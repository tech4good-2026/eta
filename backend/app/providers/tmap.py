from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx

from app.domain import ProviderLeg, ProviderRoute, ProviderWalkStep
from app.errors import ApiError
from app.models import LegMode, PlaceInput, RouteMode, RouteSearchRequest, TimeSource


class TmapRouteProvider:
    transit_url = "https://apis.openapi.sk.com/transit/routes"
    pedestrian_url = "https://apis.openapi.sk.com/tmap/routes/pedestrian"
    car_url = "https://apis.openapi.sk.com/tmap/routes"

    def __init__(self, app_key: str, client: httpx.AsyncClient) -> None:
        self.app_key = app_key
        self.client = client

    async def search(self, request: RouteSearchRequest) -> list[ProviderRoute]:
        try:
            if request.mode == RouteMode.TRANSIT:
                response = await self._request_transit(request)
                return self._parse_transit(response, request)
            if request.mode == RouteMode.WALK:
                response = await self._request_pedestrian(request)
                return [self._parse_geojson(response, request, RouteMode.WALK)]
            response = await self._request_car(request)
            return [self._parse_geojson(response, request, RouteMode.TAXI)]
        except ApiError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise self._unavailable() from error
        except (KeyError, TypeError, ValueError, IndexError) as error:
            raise ApiError(
                502,
                "UPSTREAM_INVALID_RESPONSE",
                "TMAP 응답 형식을 해석할 수 없습니다.",
                {"provider": "TMAP", "retryable": False},
            ) from error

    @property
    def headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "Content-Type": "application/json",
            "appKey": self.app_key,
        }

    async def _request_transit(self, request: RouteSearchRequest) -> dict[str, Any]:
        departure = request.departure_at or datetime.now().astimezone()
        response = await self.client.post(
            self.transit_url,
            headers=self.headers,
            json={
                "startX": str(request.origin.coordinate.longitude),
                "startY": str(request.origin.coordinate.latitude),
                "endX": str(request.destination.coordinate.longitude),
                "endY": str(request.destination.coordinate.latitude),
                "count": 5,
                "lang": 0,
                "format": "json",
                "searchDttm": departure.strftime("%Y%m%d%H%M"),
            },
        )
        return self._response_json(response)

    async def _request_pedestrian(self, request: RouteSearchRequest) -> dict[str, Any]:
        response = await self.client.post(
            self.pedestrian_url,
            params={"version": "1", "format": "json"},
            headers=self.headers,
            json={
                "startX": str(request.origin.coordinate.longitude),
                "startY": str(request.origin.coordinate.latitude),
                "endX": str(request.destination.coordinate.longitude),
                "endY": str(request.destination.coordinate.latitude),
                "startName": request.origin.name,
                "endName": request.destination.name,
                "reqCoordType": "WGS84GEO",
                "resCoordType": "WGS84GEO",
                "searchOption": "0",
            },
        )
        return self._response_json(response)

    async def _request_car(self, request: RouteSearchRequest) -> dict[str, Any]:
        response = await self.client.post(
            self.car_url,
            params={"version": "1", "format": "json"},
            headers=self.headers,
            json={
                "startX": str(request.origin.coordinate.longitude),
                "startY": str(request.origin.coordinate.latitude),
                "endX": str(request.destination.coordinate.longitude),
                "endY": str(request.destination.coordinate.latitude),
                "startName": request.origin.name,
                "endName": request.destination.name,
                "reqCoordType": "WGS84GEO",
                "resCoordType": "WGS84GEO",
                "searchOption": "0",
                "trafficInfo": "Y",
            },
        )
        return self._response_json(response)

    def _response_json(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 429:
            raise ApiError(
                429,
                "RATE_LIMITED",
                "TMAP 호출 한도를 초과했습니다.",
                {"provider": "TMAP", "retryable": True},
            )
        if response.status_code >= 500:
            raise self._unavailable()
        if response.status_code >= 400:
            raise ApiError(
                502,
                "UPSTREAM_INVALID_RESPONSE",
                "TMAP 요청을 처리할 수 없습니다.",
                {"provider": "TMAP", "upstreamStatus": response.status_code},
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise ApiError(
                502,
                "UPSTREAM_INVALID_RESPONSE",
                "TMAP이 올바른 JSON을 반환하지 않았습니다.",
                {"provider": "TMAP", "retryable": False},
            ) from error
        if not isinstance(payload, dict):
            raise ValueError("TMAP response must be an object")
        return payload

    def _parse_transit(
        self, payload: dict[str, Any], request: RouteSearchRequest
    ) -> list[ProviderRoute]:
        itineraries = payload["metaData"]["plan"]["itineraries"]
        if not isinstance(itineraries, list):
            raise ValueError("itineraries must be a list")
        departure = request.departure_at or datetime.now().astimezone()
        routes: list[ProviderRoute] = []
        for route_index, itinerary in enumerate(itineraries, start=1):
            raw_legs = itinerary["legs"]
            if not raw_legs:
                continue
            cursor = departure
            legs: list[ProviderLeg] = []
            for leg_index, raw_leg in enumerate(raw_legs, start=1):
                mode = LegMode(str(raw_leg["mode"]).upper())
                duration = int(raw_leg.get("sectionTime", 0))
                start = self._transit_place(raw_leg.get("start"), request.origin)
                end = self._transit_place(raw_leg.get("end"), request.destination)
                geometry = self._transit_geometry(raw_leg, start, end)
                provider_leg_id = f"tmap_transit_{route_index}_{leg_index}"
                steps = [
                    ProviderWalkStep(
                        instruction=str(step.get("description") or "계속 이동하세요."),
                        distance_m=int(step.get("distance", 0)),
                        geometry=geometry,
                        street_name=step.get("streetName"),
                    )
                    for step in raw_leg.get("steps", [])
                    if isinstance(step, dict)
                ]
                arrival = cursor + timedelta(seconds=duration)
                legs.append(
                    ProviderLeg(
                        provider_leg_id=provider_leg_id,
                        mode=mode,
                        start=start,
                        end=end,
                        distance_m=int(raw_leg.get("distance", 0)),
                        duration_sec=duration,
                        geometry=geometry,
                        steps=steps,
                        route_id=str(raw_leg.get("routeId") or raw_leg.get("route") or "UNKNOWN"),
                        route_name=str(raw_leg.get("route") or raw_leg.get("routeName") or mode.value),
                        line_id=str(raw_leg.get("routeId") or raw_leg.get("route") or "UNKNOWN"),
                        line_name=str(raw_leg.get("route") or raw_leg.get("routeName") or mode.value),
                        line_color=self._color(raw_leg.get("routeColor")),
                        departure_at=cursor if mode != LegMode.WALK else None,
                        arrival_at=arrival if mode != LegMode.WALK else None,
                        time_source=TimeSource.SCHEDULED,
                    )
                )
                cursor = arrival
            title_parts = [
                leg.route_name or leg.line_name
                for leg in legs
                if leg.mode in {LegMode.BUS, LegMode.SUBWAY}
            ]
            routes.append(
                ProviderRoute(
                    provider_route_id=f"tmap_transit_{route_index}",
                    mode=RouteMode.TRANSIT,
                    title=" → ".join(title_parts) or f"대중교통 경로 {route_index}",
                    standard_duration_sec=int(itinerary.get("totalTime", sum(leg.duration_sec for leg in legs))),
                    total_distance_m=int(itinerary.get("totalDistance", sum(leg.distance_m for leg in legs))),
                    walk_distance_m=int(
                        itinerary.get(
                            "totalWalkDistance",
                            sum(leg.distance_m for leg in legs if leg.mode == LegMode.WALK),
                        )
                    ),
                    transfer_count=int(itinerary.get("transferCount", 0)),
                    fare_krw=self._fare(itinerary.get("fare")),
                    legs=legs,
                )
            )
        return routes

    def _parse_geojson(
        self,
        payload: dict[str, Any],
        request: RouteSearchRequest,
        mode: RouteMode,
    ) -> ProviderRoute:
        features = payload["features"]
        if not isinstance(features, list) or not features:
            raise ValueError("features must be a non-empty list")
        summary = next(
            feature.get("properties", {})
            for feature in features
            if "totalTime" in feature.get("properties", {})
        )
        geometry: list[list[float]] = []
        steps: list[ProviderWalkStep] = []
        for feature in features:
            feature_geometry = feature.get("geometry") or {}
            if feature_geometry.get("type") != "LineString":
                continue
            coordinates = [[float(point[0]), float(point[1])] for point in feature_geometry["coordinates"]]
            if geometry and coordinates and geometry[-1] == coordinates[0]:
                geometry.extend(coordinates[1:])
            else:
                geometry.extend(coordinates)
            properties = feature.get("properties") or {}
            if mode == RouteMode.WALK:
                steps.append(
                    ProviderWalkStep(
                        instruction=str(properties.get("description") or "계속 이동하세요."),
                        distance_m=int(properties.get("distance", 0)),
                        geometry=coordinates,
                        street_name=properties.get("roadName"),
                    )
                )
        if len(geometry) < 2:
            geometry = self._line_between(request.origin, request.destination)
        distance = int(summary.get("totalDistance", 0))
        duration = int(summary.get("totalTime", 0))
        fare = int(summary.get("taxiFare") or summary.get("totalFare") or 0)
        leg_mode = LegMode.WALK if mode == RouteMode.WALK else LegMode.TAXI
        provider_id = "tmap_walk_1" if mode == RouteMode.WALK else "tmap_taxi_1"
        leg = ProviderLeg(
            provider_leg_id=f"{provider_id}_leg_1",
            mode=leg_mode,
            start=request.origin,
            end=request.destination,
            distance_m=distance,
            duration_sec=duration,
            geometry=geometry,
            steps=steps,
            expected_fare_krw=fare if mode == RouteMode.TAXI else None,
        )
        return ProviderRoute(
            provider_route_id=provider_id,
            mode=mode,
            title="계단을 피하는 도보 경로" if mode == RouteMode.WALK else "택시 예상 경로",
            standard_duration_sec=duration,
            total_distance_m=distance,
            walk_distance_m=distance if mode == RouteMode.WALK else 0,
            transfer_count=0,
            fare_krw=fare,
            legs=[leg],
        )

    @staticmethod
    def _transit_place(raw: Any, fallback: PlaceInput) -> PlaceInput:
        if not isinstance(raw, dict):
            return fallback
        longitude = raw.get("lon", raw.get("longitude"))
        latitude = raw.get("lat", raw.get("latitude"))
        if longitude is None or latitude is None:
            return fallback
        return PlaceInput(
            provider_place_id=str(raw.get("stationID")) if raw.get("stationID") else None,
            name=str(raw.get("name") or fallback.name),
            coordinate={"longitude": float(longitude), "latitude": float(latitude)},
        )

    @staticmethod
    def _transit_geometry(
        raw_leg: dict[str, Any], start: PlaceInput, end: PlaceInput
    ) -> list[list[float]]:
        linestring = (raw_leg.get("passShape") or {}).get("linestring")
        if isinstance(linestring, str):
            coordinates = []
            for pair in linestring.split():
                longitude, latitude = pair.split(",")
                coordinates.append([float(longitude), float(latitude)])
            if len(coordinates) >= 2:
                return coordinates
        return TmapRouteProvider._line_between(start, end)

    @staticmethod
    def _line_between(start: PlaceInput, end: PlaceInput) -> list[list[float]]:
        return [
            [start.coordinate.longitude, start.coordinate.latitude],
            [end.coordinate.longitude, end.coordinate.latitude],
        ]

    @staticmethod
    def _fare(value: Any) -> int:
        if isinstance(value, (int, float, str)):
            return int(value)
        if isinstance(value, dict):
            regular = value.get("regular")
            if isinstance(regular, dict):
                return int(regular.get("totalFare", 0))
            return int(value.get("totalFare", 0))
        return 0

    @staticmethod
    def _color(value: Any) -> str | None:
        if not value:
            return None
        color = str(value)
        return color if color.startswith("#") else f"#{color}"

    @staticmethod
    def _unavailable() -> ApiError:
        return ApiError(
            503,
            "UPSTREAM_UNAVAILABLE",
            "현재 TMAP 경로 정보를 불러오지 못했습니다.",
            {"provider": "TMAP", "retryable": True},
        )
