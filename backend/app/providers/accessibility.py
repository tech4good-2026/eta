from collections.abc import Callable
from datetime import datetime, timedelta

from app.domain import (
    AccessibilityContext,
    BusAccessibility,
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


class HybridAccessibilityProvider:
    """Fixture baseline enriched with Seoul elevator data when configured."""

    def __init__(
        self,
        seoul: SeoulDataClient | None = None,
        bus: SeoulBusClient | None = None,
        clock: Callable[[], datetime] | None = None,
        use_synthetic_bus: bool = True,
        walkway: WalkwaySource | None = None,
    ) -> None:
        self.seoul = seoul
        self.bus = bus
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.use_synthetic_bus = use_synthetic_bus
        self.walkway = walkway or UnknownWalkwaySource()

    async def get_context(self, routes: list[ProviderRoute]) -> AccessibilityContext:
        walk = {}
        bus = {}
        subway = {}
        for route in routes:
            for leg in route.legs:
                if leg.mode == LegMode.WALK:
                    segment = self.walkway.segment_for(
                        leg.provider_leg_id, leg.start, leg.end
                    )
                    walk[leg.provider_leg_id] = WalkAccessibility(
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
                elif leg.mode == LegMode.BUS:
                    bus[leg.provider_leg_id] = await self._bus_accessibility(
                        leg.route_name or "버스",
                        leg.start,
                    )
                elif leg.mode == LegMode.SUBWAY:
                    subway[leg.provider_leg_id] = await self._subway_accessibility(
                        leg.start.name,
                        leg.end.name,
                        leg.line_name or "지하철",
                    )
        return AccessibilityContext(walk=walk, bus=bus, subway=subway)

    async def _bus_accessibility(
        self, route_name: str, boarding_stop: PlaceInput
    ) -> BusAccessibility:
        if self.bus is None:
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
        try:
            arrivals = await self.bus.get_arrivals(route_name, boarding_stop)
        except ApiError:
            arrivals = []
        if not arrivals:
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
        try:
            boarding = await self.seoul.get_elevator(boarding_station)
            alighting = await self.seoul.get_elevator(alighting_station)
        except ApiError:
            boarding = None
            alighting = None
        if boarding is None or alighting is None:
            return StationAccessibility(
                elevator_status=FacilityStatus.UNKNOWN,
                confidence=DataConfidence.UNKNOWN,
                source=DataSource.SEOUL_OPEN_DATA,
                departures=await self._subway_departures(
                    boarding_station, line_name
                ),
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
            departures=await self._subway_departures(boarding_station, line_name),
        )

    async def _subway_departures(
        self, boarding_station: str, line_name: str
    ) -> tuple[RealtimeDeparture, ...]:
        if self.seoul is None:
            return ()
        get_arrivals = getattr(self.seoul, "get_subway_arrivals", None)
        if get_arrivals is None:
            return ()
        try:
            arrivals = await get_arrivals(boarding_station, line_name)
        except ApiError:
            return ()
        now = self.clock()
        return tuple(
            RealtimeDeparture(
                departure_at=now + timedelta(seconds=arrival.arrival_sec),
                direction=arrival.direction,
                vehicle_id=arrival.train_id,
            )
            for arrival in arrivals
        )
