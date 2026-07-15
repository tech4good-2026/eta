from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from time import monotonic
from typing import Any

import httpx

from app.errors import ApiError
from app.models import LowFloorStatus, PlaceInput


@dataclass(frozen=True)
class SeoulBusArrival:
    arrival_sec: int
    low_floor_status: LowFloorStatus
    vehicle_id: str | None = None


@dataclass(frozen=True)
class _ResolvedBusStop:
    bus_route_id: str
    station_id: str


class SeoulBusClient:
    base_url = "http://ws.bus.go.kr/api/rest"

    def __init__(
        self,
        service_key: str,
        client: httpx.AsyncClient,
        mapping_cache_ttl_sec: int = 86_400,
    ) -> None:
        self.service_key = service_key
        self.client = client
        self.mapping_cache_ttl_sec = mapping_cache_ttl_sec
        self._mapping_cache: dict[str, tuple[float, _ResolvedBusStop]] = {}

    async def get_arrivals(
        self, route_name: str, boarding_stop: PlaceInput
    ) -> list[SeoulBusArrival]:
        resolved = await self._resolve_stop(route_name, boarding_stop)
        if resolved is None:
            return []
        payload = await self._get_json(
            "/arrive/getArrInfoByRouteAll",
            {"busRouteId": resolved.bus_route_id},
        )
        row = next(
            (
                item
                for item in self._items(payload)
                if str(item.get("stId") or "") == resolved.station_id
            ),
            None,
        )
        if row is None:
            return []
        arrivals = []
        for index in (1, 2):
            arrival_sec = self._positive_int(row.get(f"exps{index}"))
            if arrival_sec is None:
                continue
            arrivals.append(
                SeoulBusArrival(
                    arrival_sec=arrival_sec,
                    low_floor_status=self._low_floor_status(
                        row.get(f"busType{index}")
                    ),
                    vehicle_id=str(row.get(f"vehId{index}") or "") or None,
                )
            )
        return sorted(arrivals, key=lambda value: value.arrival_sec)

    async def _resolve_stop(
        self, route_name: str, boarding_stop: PlaceInput
    ) -> _ResolvedBusStop | None:
        route_number = self._route_number(route_name)
        cache_key = (
            f"{route_number}:{boarding_stop.name}:"
            f"{boarding_stop.coordinate.latitude:.5f}:"
            f"{boarding_stop.coordinate.longitude:.5f}"
        )
        now = monotonic()
        cached = self._mapping_cache.get(cache_key)
        if cached is not None and now < cached[0]:
            return cached[1]

        routes_payload = await self._get_json(
            "/busRouteInfo/getBusRouteList", {"strSrch": route_number}
        )
        route = self._select_route(self._items(routes_payload), route_number)
        if route is None:
            return None
        bus_route_id = str(route.get("busRouteId") or "")
        if not bus_route_id:
            return None

        stations_payload = await self._get_json(
            "/busRouteInfo/getStaionByRoute", {"busRouteId": bus_route_id}
        )
        station = self._select_station(self._items(stations_payload), boarding_stop)
        if station is None:
            return None
        station_id = str(station.get("station") or station.get("stId") or "")
        if not station_id:
            return None
        resolved = _ResolvedBusStop(
            bus_route_id=bus_route_id,
            station_id=station_id,
        )
        self._mapping_cache[cache_key] = (
            now + self.mapping_cache_ttl_sec,
            resolved,
        )
        return resolved

    async def _get_json(
        self, endpoint: str, query: dict[str, str]
    ) -> dict[str, Any]:
        params = {
            "serviceKey": self.service_key,
            "resultType": "json",
            **query,
        }
        try:
            response = await self.client.get(f"{self.base_url}{endpoint}", params=params)
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise self._unavailable() from error
        if response.status_code >= 400:
            raise self._unavailable()
        try:
            payload = response.json()
        except ValueError as error:
            raise self._invalid_response("서울 버스 API가 JSON을 반환하지 않았습니다.") from error
        if not isinstance(payload, dict):
            raise self._invalid_response("서울 버스 API 응답 형식이 올바르지 않습니다.")
        header = payload.get("msgHeader") or {}
        code = str(header.get("headerCd") or "0")
        if code != "0":
            raise ApiError(
                502,
                "UPSTREAM_AUTH_OR_REQUEST_FAILED",
                "서울 버스 API 요청이 거부되었습니다.",
                {
                    "provider": "SEOUL_BUS",
                    "upstreamCode": code,
                    "upstreamMessage": str(header.get("headerMsg") or ""),
                },
            )
        return payload

    @staticmethod
    def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw = (payload.get("msgBody") or {}).get("itemList") or []
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            raise SeoulBusClient._invalid_response(
                "서울 버스 API 목록 형식이 올바르지 않습니다."
            )
        return [item for item in raw if isinstance(item, dict)]

    @classmethod
    def _select_route(
        cls, routes: list[dict[str, Any]], route_number: str
    ) -> dict[str, Any] | None:
        expected = cls._route_key(route_number)
        exact = [
            route
            for route in routes
            if cls._route_key(
                str(route.get("busRouteNm") or route.get("busRouteAbrv") or "")
            )
            == expected
        ]
        return exact[0] if exact else None

    @classmethod
    def _select_station(
        cls, stations: list[dict[str, Any]], boarding_stop: PlaceInput
    ) -> dict[str, Any] | None:
        expected_name = cls._station_key(boarding_stop.name)
        candidates = [
            station
            for station in stations
            if cls._station_key(str(station.get("stationNm") or "")) == expected_name
        ]
        if not candidates:
            candidates = stations
        located = []
        for station in candidates:
            try:
                longitude = float(station.get("gpsX"))
                latitude = float(station.get("gpsY"))
            except (TypeError, ValueError):
                continue
            located.append(
                (
                    cls._distance_m(
                        boarding_stop.coordinate.latitude,
                        boarding_stop.coordinate.longitude,
                        latitude,
                        longitude,
                    ),
                    station,
                )
            )
        if located:
            return min(located, key=lambda value: value[0])[1]
        return candidates[0] if candidates else None

    @staticmethod
    def _route_number(route_name: str) -> str:
        return route_name.rsplit(":", maxsplit=1)[-1].strip()

    @staticmethod
    def _route_key(value: str) -> str:
        return value.replace(" ", "").casefold()

    @staticmethod
    def _station_key(value: str) -> str:
        return "".join(character for character in value if character.isalnum()).casefold()

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _low_floor_status(value: Any) -> LowFloorStatus:
        code = str(value)
        if code == "1":
            return LowFloorStatus.CONFIRMED
        if code == "0":
            return LowFloorStatus.NOT_LOW_FLOOR
        return LowFloorStatus.UNKNOWN

    @staticmethod
    def _distance_m(
        first_latitude: float,
        first_longitude: float,
        second_latitude: float,
        second_longitude: float,
    ) -> float:
        first_latitude_rad = radians(first_latitude)
        second_latitude_rad = radians(second_latitude)
        delta_latitude = second_latitude_rad - first_latitude_rad
        delta_longitude = radians(second_longitude - first_longitude)
        value = sin(delta_latitude / 2) ** 2 + (
            cos(first_latitude_rad)
            * cos(second_latitude_rad)
            * sin(delta_longitude / 2) ** 2
        )
        return 2 * 6_371_000 * asin(sqrt(value))

    @staticmethod
    def _unavailable() -> ApiError:
        return ApiError(
            503,
            "UPSTREAM_UNAVAILABLE",
            "서울 버스 실시간 정보를 불러오지 못했습니다.",
            {"provider": "SEOUL_BUS", "retryable": True},
        )

    @staticmethod
    def _invalid_response(message: str) -> ApiError:
        return ApiError(
            502,
            "UPSTREAM_INVALID_RESPONSE",
            message,
            {"provider": "SEOUL_BUS", "retryable": False},
        )
