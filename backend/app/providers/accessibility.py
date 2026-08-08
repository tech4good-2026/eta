import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import TypeVar

from app.domain import (
    AccessibilityContext,
    BusAccessibility,
    FacilityUnit,
    ProviderRoute,
    RealtimeDeparture,
    StationAccessibility,
    WalkAccessibility,
)
from app.errors import ApiError
from app.models import (
    DataConfidence,
    DataSource,
    FacilityStatus,
    LegMode,
    LowFloorStatus,
    PlaceInput,
)
from app.providers.seoul import SeoulDataClient
from app.providers.seoul_bus import SeoulBusClient
from app.providers.walkway import UnknownWalkwaySource, WalkwaySource


T = TypeVar("T")

#: provider 하나를 기다리는 한도. 넘기면 그 항목만 '확인 안 됨'으로 내려가고
#: 나머지 응답은 그대로 나간다. 이 서비스에서 늦은 안내는 틀린 안내와 같다.
DEFAULT_PROVIDER_TIMEOUT_SEC = 3.0


class HybridAccessibilityProvider:
    """Fixture baseline enriched with Seoul elevator data when configured."""

    def __init__(
        self,
        seoul: SeoulDataClient | None = None,
        bus: SeoulBusClient | None = None,
        clock: Callable[[], datetime] | None = None,
        use_synthetic_bus: bool = True,
        walkway: WalkwaySource | None = None,
        synthetic_bus_fallback: bool = False,
        provider_timeout_sec: float | None = DEFAULT_PROVIDER_TIMEOUT_SEC,
    ) -> None:
        self.seoul = seoul
        self.bus = bus
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.use_synthetic_bus = use_synthetic_bus
        self.walkway = walkway or UnknownWalkwaySource()
        # 실시간 버스 도착을 얻지 못했을 때 데모용 목업 도착정보를 만들지 여부.
        self.synthetic_bus_fallback = synthetic_bus_fallback
        self.provider_timeout_sec = provider_timeout_sec

    async def _guard(self, awaitable: Awaitable[T], fallback: T) -> T:
        """외부 응답 하나가 실패하거나 늦어도 나머지를 붙들지 않는다.

        늦은 것과 못 받은 것을 같게 다룬다 — 어느 쪽이든 우리가 아는 건 '확인 안 됨'이다.
        """
        try:
            if self.provider_timeout_sec is None:
                return await awaitable
            return await asyncio.wait_for(awaitable, self.provider_timeout_sec)
        except (ApiError, TimeoutError):
            return fallback

    async def get_context(self, routes: list[ProviderRoute]) -> AccessibilityContext:
        """경로 후보 전체의 접근성 정보를 한 번에 모아 온다.

        예전에는 경로마다, 그 안의 구간마다 외부를 차례로 물었다. 구간이 늘면 응답 시간이
        호출들의 **합**이 됐다. 구간끼리는 서로 필요로 하는 게 없으므로 같이 물으면
        **가장 느린 하나**로 끝난다.

        같은 역·같은 버스 정류장이 여러 경로 후보에 겹쳐 나오는 것도 흔하다. 그때는
        한 번만 묻고 결과를 나눠 쓴다.
        """
        walk: dict[str, WalkAccessibility] = {}
        bus_key_of_leg: dict[str, tuple] = {}
        subway_key_of_leg: dict[str, tuple] = {}
        bus_calls: dict[tuple, tuple[str, PlaceInput]] = {}
        subway_calls: dict[tuple, tuple[str, str, str]] = {}

        for route in routes:
            for leg in route.legs:
                if leg.mode == LegMode.WALK:
                    walk[leg.provider_leg_id] = self._walk_accessibility(leg)
                elif leg.mode == LegMode.BUS:
                    route_name = leg.route_name or "버스"
                    key = self._bus_key(route_name, leg.start)
                    bus_key_of_leg[leg.provider_leg_id] = key
                    bus_calls.setdefault(key, (route_name, leg.start))
                elif leg.mode == LegMode.SUBWAY:
                    args = (leg.start.name, leg.end.name, leg.line_name or "지하철")
                    subway_key_of_leg[leg.provider_leg_id] = args
                    subway_calls.setdefault(args, args)

        bus_keys = list(bus_calls)
        subway_keys = list(subway_calls)
        answers = await asyncio.gather(
            *(self._bus_accessibility(*bus_calls[key]) for key in bus_keys),
            *(self._subway_accessibility(*subway_calls[key]) for key in subway_keys),
        )
        bus_answer = dict(zip(bus_keys, answers[: len(bus_keys)]))
        subway_answer = dict(zip(subway_keys, answers[len(bus_keys) :]))

        return AccessibilityContext(
            walk=walk,
            bus={leg_id: bus_answer[key] for leg_id, key in bus_key_of_leg.items()},
            subway={
                leg_id: subway_answer[key] for leg_id, key in subway_key_of_leg.items()
            },
        )

    @staticmethod
    def _bus_key(route_name: str, boarding_stop: PlaceInput) -> tuple:
        """버스 provider가 스스로 쓰는 것과 같은 기준으로 같은 정류장인지 본다."""
        return (
            route_name,
            boarding_stop.name,
            round(boarding_stop.coordinate.latitude, 5),
            round(boarding_stop.coordinate.longitude, 5),
        )

    def _walk_accessibility(self, leg) -> WalkAccessibility:
        segment = self.walkway.segment_for(leg.provider_leg_id, leg.start, leg.end)
        return WalkAccessibility(
            has_stairs=segment.has_stairs,
            max_slope_percent=segment.max_slope_percent,
            surface_type=segment.surface_type,
            width_m=segment.width_m,
            curb_ramp_present=segment.curb_ramp_present,
            tactile_paving_present=segment.tactile_paving_present,
            passable=segment.passable,
            confidence=segment.confidence,
            source=segment.source,
        )

    async def _bus_accessibility(
        self, route_name: str, boarding_stop: PlaceInput
    ) -> BusAccessibility:
        if self.bus is None:
            if self.synthetic_bus_fallback:
                return self._synthetic_bus(route_name)
            if not self.use_synthetic_bus:
                return BusAccessibility(
                    low_floor_status=LowFloorStatus.UNKNOWN,
                    confidence=DataConfidence.UNKNOWN,
                    source=DataSource.UNKNOWN,
                )
            return BusAccessibility(
                low_floor_status=LowFloorStatus.CONFIRMED,
                confidence=DataConfidence.ESTIMATED,
                source=DataSource.SYNTHETIC_FIXTURE,
            )
        arrivals = await self._guard(
            self.bus.get_arrivals(route_name, boarding_stop), []
        )
        if not arrivals:
            if self.synthetic_bus_fallback:
                return self._synthetic_bus(route_name)
            return BusAccessibility(
                low_floor_status=LowFloorStatus.UNKNOWN,
                confidence=DataConfidence.UNKNOWN,
                source=DataSource.SEOUL_OPEN_DATA,
            )
        now = self.clock()
        departures = tuple(
            RealtimeDeparture(
                departure_at=now + timedelta(seconds=arrival.arrival_sec),
                low_floor_status=arrival.low_floor_status,
                vehicle_id=arrival.vehicle_id,
            )
            for arrival in arrivals
        )
        statuses = {arrival.low_floor_status for arrival in arrivals}
        if LowFloorStatus.CONFIRMED in statuses:
            status = LowFloorStatus.CONFIRMED
        elif statuses == {LowFloorStatus.NOT_LOW_FLOOR}:
            status = LowFloorStatus.NOT_LOW_FLOOR
        else:
            status = LowFloorStatus.UNKNOWN
        return BusAccessibility(
            low_floor_status=status,
            confidence=DataConfidence.VERIFIED,
            source=DataSource.SEOUL_OPEN_DATA,
            departures=departures,
        )

    def _synthetic_bus(self, route_name: str) -> BusAccessibility:
        """데모용 목업 저상버스 도착정보. 노선명 기반 결정론적 값이며
        SYNTHETIC_FIXTURE로 표시된다. 실제 도착정보를 얻으면 사용되지 않는다."""
        seed = int(hashlib.sha256(route_name.encode("utf-8")).hexdigest()[:8], 16)
        # 다음 저상버스 대기 4~23분: 일부 노선은 대기가 길어 콜택시 추천이 발동된다.
        first_wait_sec = (4 + seed % 20) * 60
        now = self.clock()
        departures = (
            RealtimeDeparture(
                departure_at=now + timedelta(seconds=first_wait_sec),
                low_floor_status=LowFloorStatus.CONFIRMED,
                vehicle_id=f"mock-{seed % 1000}",
            ),
            RealtimeDeparture(
                departure_at=now + timedelta(seconds=first_wait_sec + 720),
                low_floor_status=LowFloorStatus.CONFIRMED,
                vehicle_id=f"mock-{seed % 1000 + 1}",
            ),
        )
        return BusAccessibility(
            low_floor_status=LowFloorStatus.CONFIRMED,
            confidence=DataConfidence.ESTIMATED,
            source=DataSource.SYNTHETIC_FIXTURE,
            departures=departures,
        )

    async def _subway_accessibility(
        self,
        boarding_station: str,
        alighting_station: str,
        line_name: str,
    ) -> StationAccessibility:
        if self.seoul is None:
            return StationAccessibility(
                elevator_status=FacilityStatus.AVAILABLE,
                confidence=DataConfidence.ESTIMATED,
                location_description="해커톤 합성 fixture",
                source=DataSource.SYNTHETIC_FIXTURE,
            )
        # 다섯 가지 모두 서로를 필요로 하지 않는다. 예전에는 차례로 기다렸다.
        (
            boarding,
            alighting,
            boarding_units,
            alighting_units,
            departures,
        ) = await asyncio.gather(
            self._guard(self.seoul.get_elevator(boarding_station), None),
            self._guard(self.seoul.get_elevator(alighting_station), None),
            self._station_units(boarding_station),
            self._station_units(alighting_station),
            self._subway_departures(boarding_station, line_name),
        )
        if boarding is None or alighting is None:
            return StationAccessibility(
                elevator_status=FacilityStatus.UNKNOWN,
                confidence=DataConfidence.UNKNOWN,
                source=DataSource.SEOUL_OPEN_DATA,
                departures=departures,
                boarding_units=boarding_units,
                alighting_units=alighting_units,
            )
        statuses = {boarding.status, alighting.status}
        status = (
            FacilityStatus.UNAVAILABLE
            if FacilityStatus.UNAVAILABLE in statuses
            else FacilityStatus.AVAILABLE
        )
        descriptions = [
            f"{station}: {facility.location_description}"
            for station, facility in [
                (boarding_station, boarding),
                (alighting_station, alighting),
            ]
            if facility.location_description
        ]
        return StationAccessibility(
            elevator_status=status,
            confidence=(
                DataConfidence.VERIFIED
                if boarding.confidence == alighting.confidence == DataConfidence.VERIFIED
                else DataConfidence.ESTIMATED
            ),
            location_description=" / ".join(descriptions) or None,
            observed_at=self.clock(),
            source=DataSource.SEOUL_OPEN_DATA,
            departures=departures,
            boarding_units=boarding_units,
            alighting_units=alighting_units,
        )

    async def _station_units(self, station_name: str) -> tuple[FacilityUnit, ...]:
        """역사 내 엘리베이터 개별 위치(방면·출구·운행층) 목록을 실데이터로 조회한다."""
        if self.seoul is None:
            return ()
        get_units = getattr(self.seoul, "get_station_elevators", None)
        if get_units is None:
            return ()
        units = await self._guard(get_units(station_name), [])
        return tuple(
            FacilityUnit(
                station_name=unit.station_name,
                location_description=unit.location_description,
                floors=unit.floors,
                status=unit.status,
            )
            for unit in units
        )

    async def _subway_departures(
        self, boarding_station: str, line_name: str
    ) -> tuple[RealtimeDeparture, ...]:
        if self.seoul is None:
            return ()
        get_arrivals = getattr(self.seoul, "get_subway_arrivals", None)
        if get_arrivals is None:
            return ()
        arrivals = await self._guard(get_arrivals(boarding_station, line_name), [])
        now = self.clock()
        return tuple(
            RealtimeDeparture(
                departure_at=now + timedelta(seconds=arrival.arrival_sec),
                direction=arrival.direction,
                vehicle_id=arrival.train_id,
            )
            for arrival in arrivals
        )
