from __future__ import annotations

from datetime import datetime, timedelta
from math import ceil
from typing import Protocol

from app.domain import AccessibilityContext, ProviderLeg, ProviderRoute
from app.models import (
    AccessibilityStatus,
    BusLeg,
    DataConfidence,
    DataSource,
    FacilityStatus,
    GeoJsonLineString,
    LegMode,
    LowFloorStatus,
    MobilityAid,
    Notice,
    Route,
    RouteSummary,
    StationFacility,
    SubwayLeg,
    SurfaceType,
    TaxiLeg,
    TimeSource,
    UserProfile,
    WalkLeg,
    WalkStep,
)


class PersonalizationEngine(Protocol):
    def personalize_routes(
        self,
        provider_routes: list[ProviderRoute],
        profile: UserProfile,
        context: AccessibilityContext,
        requested_at: datetime,
    ) -> list[Route]: ...


STATUS_ORDER = {
    AccessibilityStatus.ACCESSIBLE: 0,
    AccessibilityStatus.CAUTION: 1,
    AccessibilityStatus.UNAVAILABLE: 2,
}
CONFIDENCE_ORDER = {
    DataConfidence.VERIFIED: 0,
    DataConfidence.ESTIMATED: 1,
    DataConfidence.UNKNOWN: 2,
}


class BaselinePersonalizationEngine:
    """Deterministic baseline that can be replaced behind PersonalizationEngine."""

    steep_slope_threshold_percent = 6.0
    accessible_boarding_buffer_sec = 60

    # 도보 환경 패널티 계수. 바퀴형 보조기구(휠체어·유모차)는 계수를 크게 둔다.
    wheeled_aids = frozenset(
        {
            MobilityAid.MANUAL_WHEELCHAIR,
            MobilityAid.POWER_WHEELCHAIR,
            MobilityAid.STROLLER,
        }
    )
    rough_surfaces = frozenset(
        {SurfaceType.STONE, SurfaceType.BRICK, SurfaceType.UNPAVED}
    )
    comfortable_slope_percent = 3.0
    slope_penalty_per_percent = 0.04
    wheeled_slope_penalty_per_percent = 0.10
    rough_surface_penalty = 0.10
    wheeled_rough_surface_penalty = 0.30
    min_comfortable_width_m = 1.2
    narrow_width_penalty = 0.10
    wheeled_narrow_width_penalty = 0.35
    missing_curb_ramp_penalty = 0.20
    wheeled_missing_curb_ramp_penalty = 1.50
    max_walk_penalty = 3.0

    def personalize_routes(
        self,
        provider_routes: list[ProviderRoute],
        profile: UserProfile,
        context: AccessibilityContext,
        requested_at: datetime,
    ) -> list[Route]:
        routes = [self._personalize(candidate, profile, context, requested_at) for candidate in provider_routes]
        routes.sort(
            key=lambda route: (
                STATUS_ORDER[AccessibilityStatus(route.accessibility_status)],
                route.summary.personalized_duration_sec,
            )
        )
        return [replace_rank(route, rank) for rank, route in enumerate(routes, start=1)]

    def _personalize(
        self,
        candidate: ProviderRoute,
        profile: UserProfile,
        context: AccessibilityContext,
        requested_at: datetime,
    ) -> Route:
        warnings: list[Notice] = []
        unavailable: list[Notice] = []
        confidences: list[DataConfidence] = []
        legs = []
        cursor = requested_at

        for provider_leg in candidate.legs:
            if provider_leg.mode == LegMode.WALK:
                leg, leg_warnings, leg_unavailable, confidence = self._walk_leg(
                    provider_leg, profile, context
                )
            elif provider_leg.mode == LegMode.BUS:
                leg, leg_warnings, leg_unavailable, confidence = self._bus_leg(
                    provider_leg, profile, context, cursor
                )
            elif provider_leg.mode == LegMode.SUBWAY:
                leg, leg_warnings, leg_unavailable, confidence = self._subway_leg(
                    provider_leg, profile, context, cursor
                )
            else:
                leg, leg_warnings, leg_unavailable, confidence = self._taxi_leg(
                    provider_leg, profile
                )
            legs.append(leg)
            warnings.extend(leg_warnings)
            unavailable.extend(leg_unavailable)
            confidences.append(confidence)
            if leg.mode in {LegMode.BUS, LegMode.SUBWAY}:
                cursor = max(cursor, leg.arrival_at)
            else:
                cursor += timedelta(seconds=leg.personalized_duration_sec)

        summed_standard = sum(leg.standard_duration_sec for leg in legs)
        non_leg_time = max(0, candidate.standard_duration_sec - summed_standard)
        duration_from_legs = non_leg_time + sum(
            leg.personalized_duration_sec for leg in legs
        )
        duration_from_timeline = max(
            0,
            ceil((cursor - requested_at).total_seconds()),
        )
        personalized_duration = max(duration_from_legs, duration_from_timeline)
        if personalized_duration > candidate.standard_duration_sec:
            extra_minutes = ceil((personalized_duration - candidate.standard_duration_sec) / 60)
            warnings.insert(
                0,
                Notice(
                    code="PERSONALIZED_TIME_LONGER",
                    severity="INFO",
                    message=f"개인 이동속도를 반영하면 일반 안내보다 {extra_minutes}분 더 걸립니다.",
                ),
            )

        status = AccessibilityStatus.ACCESSIBLE
        if unavailable:
            status = AccessibilityStatus.UNAVAILABLE
        elif any(warning.severity != "INFO" for warning in warnings):
            status = AccessibilityStatus.CAUTION
        if candidate.mode == "TAXI":
            status = AccessibilityStatus.CAUTION

        confidence = max(confidences, key=lambda value: CONFIDENCE_ORDER[value])
        return Route(
            route_id=f"route_{candidate.provider_route_id}",
            rank=1,
            mode=candidate.mode,
            title=candidate.title,
            accessibility_status=status,
            data_confidence=confidence,
            summary=RouteSummary(
                standard_duration_sec=candidate.standard_duration_sec,
                personalized_duration_sec=personalized_duration,
                departure_at=requested_at,
                arrival_at=requested_at + timedelta(seconds=personalized_duration),
                total_distance_m=candidate.total_distance_m,
                walk_distance_m=candidate.walk_distance_m,
                transfer_count=candidate.transfer_count,
                fare_krw=candidate.fare_krw,
            ),
            warnings=warnings,
            unavailable_reasons=unavailable,
            legs=legs,
        )

    def _walk_leg(self, leg: ProviderLeg, profile: UserProfile, context: AccessibilityContext):
        value = context.walk.get(leg.provider_leg_id)
        confidence = value.confidence if value else DataConfidence.UNKNOWN
        has_stairs = value.has_stairs if value else None
        slope = value.max_slope_percent if value else None
        warnings: list[Notice] = []
        unavailable: list[Notice] = []

        if profile.preferences.avoid_stairs:
            if value is None or value.has_stairs is None:
                warnings.append(self._notice("STAIR_DATA_UNKNOWN", "계단 정보가 확인되지 않았습니다.", leg))
            elif value.has_stairs:
                unavailable.append(self._notice("STAIRS_MUST_BE_AVOIDED", "계단이 포함된 경로입니다.", leg, critical=True))
        if profile.preferences.avoid_steep_slopes:
            if slope is None:
                warnings.append(self._notice("SLOPE_DATA_UNKNOWN", "경사 정보가 확인되지 않았습니다.", leg))
            elif slope > self.steep_slope_threshold_percent:
                unavailable.append(self._notice("STEEP_SLOPE_MUST_BE_AVOIDED", "급경사가 포함된 경로입니다.", leg, critical=True))

        if value is not None and not value.passable:
            unavailable.append(self._notice("WALKWAY_BLOCKED", "현재 통행이 제한된 보도 구간입니다.", leg, critical=True))

        base_sec = ceil(leg.distance_m / profile.walking_speed.walking_speed_mps)
        penalty, penalty_warnings = self._walk_penalty(value, profile, leg)
        warnings.extend(penalty_warnings)
        personalized = max(leg.duration_sec, ceil(base_sec * (1 + penalty)))
        steps = [
            WalkStep(
                instruction=step.instruction,
                distance_m=step.distance_m,
                street_name=step.street_name,
                geometry=GeoJsonLineString(coordinates=step.geometry),
            )
            for step in leg.steps
        ]
        if not steps:
            steps = [
                WalkStep(
                    instruction=f"{leg.end.name}까지 이동하세요.",
                    distance_m=leg.distance_m,
                    geometry=GeoJsonLineString(coordinates=leg.geometry),
                )
            ]
        return (
            WalkLeg(
                leg_id=leg.provider_leg_id,
                start=leg.start,
                end=leg.end,
                distance_m=leg.distance_m,
                standard_duration_sec=leg.duration_sec,
                personalized_duration_sec=personalized,
                geometry=GeoJsonLineString(coordinates=leg.geometry),
                steps=steps,
                max_slope_percent=slope,
                has_stairs=has_stairs,
                surface_type=value.surface_type if value else None,
                width_m=value.width_m if value else None,
                curb_ramp_present=value.curb_ramp_present if value else None,
                tactile_paving_present=value.tactile_paving_present if value else None,
                passable=value.passable if value else True,
                data_confidence=confidence,
                data_source=value.source if value else DataSource.UNKNOWN,
            ),
            warnings,
            unavailable,
            confidence,
        )

    def _walk_penalty(self, value, profile: UserProfile, leg: ProviderLeg):
        """도로 난이도(경사·노면·폭·턱낮춤)를 보행 시간 배수로 환산한다.

        결과 배수는 1 이상이며(계약상 개인화 시간은 기본값보다 짧아질 수 없다),
        바퀴형 보조기구 사용자는 동일 조건에서 더 큰 패널티를 받는다.
        """
        warnings: list[Notice] = []
        if value is None:
            return 0.0, warnings
        wheeled = bool(set(profile.mobility_aids) & self.wheeled_aids)
        penalty = 0.0

        slope = value.max_slope_percent
        if slope is not None and slope > self.comfortable_slope_percent:
            coeff = (
                self.wheeled_slope_penalty_per_percent
                if wheeled
                else self.slope_penalty_per_percent
            )
            penalty += (slope - self.comfortable_slope_percent) * coeff
            warnings.append(
                self._info("STEEP_SLOPE_SLOWDOWN", f"경사 약 {slope:.0f}% 구간으로 이동 시간이 늘어납니다.", leg)
            )
        if value.surface_type in self.rough_surfaces:
            penalty += (
                self.wheeled_rough_surface_penalty
                if wheeled
                else self.rough_surface_penalty
            )
            warnings.append(
                self._info("ROUGH_SURFACE", "노면이 고르지 않아 이동 시간이 늘어납니다.", leg)
            )
        if value.width_m is not None and value.width_m < self.min_comfortable_width_m:
            penalty += (
                self.wheeled_narrow_width_penalty if wheeled else self.narrow_width_penalty
            )
            if wheeled:
                warnings.append(
                    self._info("NARROW_WALKWAY", "보도 폭이 좁아 통행이 더딜 수 있습니다.", leg)
                )
        if value.curb_ramp_present is False:
            if wheeled:
                penalty += self.wheeled_missing_curb_ramp_penalty
                warnings.append(
                    self._notice("MISSING_CURB_RAMP", "턱낮춤이 없는 횡단 구간으로 이동이 크게 지연됩니다.", leg)
                )
            else:
                penalty += self.missing_curb_ramp_penalty
        return min(penalty, self.max_walk_penalty), warnings

    def _bus_leg(
        self,
        leg: ProviderLeg,
        profile: UserProfile,
        context: AccessibilityContext,
        earliest_boarding_at: datetime,
    ):
        value = context.bus.get(leg.provider_leg_id)
        selected_departure = None
        if value and value.departures:
            catchable_at = earliest_boarding_at + timedelta(
                seconds=self.accessible_boarding_buffer_sec
            )
            catchable = sorted(
                (
                    departure
                    for departure in value.departures
                    if departure.departure_at >= catchable_at
                ),
                key=lambda departure: departure.departure_at,
            )
            if profile.preferences.low_floor_bus_required:
                accessible = [
                    departure
                    for departure in catchable
                    if departure.low_floor_status == LowFloorStatus.CONFIRMED
                ]
                selected_departure = accessible[0] if accessible else (
                    catchable[0] if catchable else None
                )
            else:
                selected_departure = catchable[0] if catchable else None
        low_floor = (
            selected_departure.low_floor_status
            if selected_departure is not None
            else value.low_floor_status
            if value and not value.departures
            else LowFloorStatus.UNKNOWN
        )
        confidence = value.confidence if value else DataConfidence.UNKNOWN
        warnings: list[Notice] = []
        unavailable: list[Notice] = []
        if profile.preferences.low_floor_bus_required:
            if low_floor == LowFloorStatus.NOT_LOW_FLOOR:
                unavailable.append(self._notice("LOW_FLOOR_BUS_REQUIRED", "저상버스가 아닌 차량입니다.", leg, critical=True))
            elif low_floor != LowFloorStatus.CONFIRMED:
                warnings.append(self._notice("LOW_FLOOR_STATUS_UNKNOWN", "저상버스 운행 여부를 확인해 주세요.", leg))
        if selected_departure is not None:
            departure = selected_departure.departure_at
            time_source = TimeSource.REALTIME
        else:
            departure = max(leg.departure_at or earliest_boarding_at, earliest_boarding_at)
            time_source = leg.time_source
        arrival = departure + timedelta(seconds=leg.duration_sec)
        return (
            BusLeg(
                leg_id=leg.provider_leg_id,
                start=leg.start,
                end=leg.end,
                distance_m=leg.distance_m,
                standard_duration_sec=leg.duration_sec,
                personalized_duration_sec=leg.duration_sec,
                geometry=GeoJsonLineString(coordinates=leg.geometry),
                route_id=leg.route_id or "UNKNOWN",
                route_name=leg.route_name or "버스",
                boarding_stop=leg.start,
                alighting_stop=leg.end,
                low_floor_status=low_floor,
                departure_at=departure,
                arrival_at=arrival,
                time_source=time_source,
                data_confidence=confidence,
                data_source=value.source if value else DataSource.UNKNOWN,
            ),
            warnings,
            unavailable,
            confidence,
        )

    def _subway_leg(
        self,
        leg: ProviderLeg,
        profile: UserProfile,
        context: AccessibilityContext,
        earliest_boarding_at: datetime,
    ):
        value = context.subway.get(leg.provider_leg_id)
        elevator = value.elevator_status if value and value.elevator_status else FacilityStatus.UNKNOWN
        confidence = value.confidence if value else DataConfidence.UNKNOWN
        warnings: list[Notice] = []
        unavailable: list[Notice] = []
        if profile.preferences.elevator_required:
            if elevator == FacilityStatus.UNAVAILABLE:
                unavailable.append(self._notice("ELEVATOR_REQUIRED", "이용 가능한 엘리베이터가 없습니다.", leg, critical=True))
            elif elevator == FacilityStatus.UNKNOWN:
                warnings.append(self._notice("ELEVATOR_STATUS_UNKNOWN", "엘리베이터 상태가 확인되지 않았습니다.", leg))
        catchable_at = earliest_boarding_at + timedelta(
            seconds=self.accessible_boarding_buffer_sec
        )
        departures = sorted(
            (
                departure
                for departure in value.departures
                if departure.departure_at >= catchable_at
            ),
            key=lambda departure: departure.departure_at,
        ) if value else []
        selected_departure = departures[0] if departures else None
        if selected_departure is not None:
            departure = selected_departure.departure_at
            time_source = TimeSource.REALTIME
        else:
            departure = max(leg.departure_at or earliest_boarding_at, earliest_boarding_at)
            time_source = leg.time_source
        arrival = departure + timedelta(seconds=leg.duration_sec)
        facilities: list[StationFacility] = []
        # 역사 내 엘리베이터 개별 위치(방면·출구·운행층)를 승차역/하차역 좌표에
        # 붙여 지도 표시가 가능하게 한다.
        for units, place in (
            (value.boarding_units if value else (), leg.start),
            (value.alighting_units if value else (), leg.end),
        ):
            for unit in units:
                detail = " · ".join(
                    part
                    for part in (unit.location_description, unit.floors)
                    if part
                )
                facilities.append(
                    StationFacility(
                        type="ELEVATOR",
                        status=unit.status,
                        location_description=detail or None,
                        observed_at=value.observed_at if value else None,
                        station_name=unit.station_name,
                        coordinate=place.coordinate,
                        data_confidence=confidence,
                        data_source=value.source if value else DataSource.UNKNOWN,
                    )
                )
        if not facilities:
            facilities = [
                StationFacility(
                    type="ELEVATOR",
                    status=elevator,
                    location_description=value.location_description if value else None,
                    observed_at=value.observed_at if value else None,
                    data_confidence=confidence,
                    data_source=value.source if value else DataSource.UNKNOWN,
                )
            ]
        return (
            SubwayLeg(
                leg_id=leg.provider_leg_id,
                start=leg.start,
                end=leg.end,
                distance_m=leg.distance_m,
                standard_duration_sec=leg.duration_sec,
                personalized_duration_sec=leg.duration_sec,
                geometry=GeoJsonLineString(coordinates=leg.geometry),
                line_id=leg.line_id or "UNKNOWN",
                line_name=leg.line_name or "지하철",
                line_color=leg.line_color,
                boarding_station=leg.start,
                alighting_station=leg.end,
                departure_at=departure,
                arrival_at=arrival,
                time_source=time_source,
                facilities=facilities,
                data_confidence=confidence,
            ),
            warnings,
            unavailable,
            confidence,
        )

    def _taxi_leg(self, leg: ProviderLeg, profile: UserProfile):
        warnings: list[Notice] = []
        if profile.mobility_aids:
            warnings.append(self._notice("WHEELCHAIR_TAXI_NOT_GUARANTEED", "이동 보조기구 탑승 가능 차량을 보장하지 않습니다.", leg))
        return (
            TaxiLeg(
                leg_id=leg.provider_leg_id,
                start=leg.start,
                end=leg.end,
                distance_m=leg.distance_m,
                standard_duration_sec=leg.duration_sec,
                personalized_duration_sec=leg.duration_sec,
                geometry=GeoJsonLineString(coordinates=leg.geometry),
                expected_fare_krw=leg.expected_fare_krw or 0,
                time_source=TimeSource.ESTIMATED,
            ),
            warnings,
            [],
            DataConfidence.ESTIMATED,
        )

    @staticmethod
    def _notice(code: str, message: str, leg: ProviderLeg, critical: bool = False) -> Notice:
        return Notice(
            code=code,
            severity="CRITICAL" if critical else "WARNING",
            message=message,
            leg_id=leg.provider_leg_id,
        )

    @staticmethod
    def _info(code: str, message: str, leg: ProviderLeg) -> Notice:
        return Notice(
            code=code,
            severity="INFO",
            message=message,
            leg_id=leg.provider_leg_id,
        )


def replace_rank(route: Route, rank: int) -> Route:
    return route.model_copy(update={"rank": rank})
