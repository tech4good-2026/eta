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
    Notice,
    Route,
    RouteSummary,
    StationFacility,
    SubwayLeg,
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
        has_stairs = value.has_stairs if value and value.has_stairs is not None else False
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

        personalized = max(
            leg.duration_sec,
            ceil(leg.distance_m / profile.walking_speed.walking_speed_mps),
        )
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
                data_confidence=confidence,
                data_source=value.source if value else DataSource.UNKNOWN,
            ),
            warnings,
            unavailable,
            confidence,
        )

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
        facility = StationFacility(
            type="ELEVATOR",
            status=elevator,
            location_description=value.location_description if value else None,
            observed_at=value.observed_at if value else None,
            data_confidence=confidence,
            data_source=value.source if value else DataSource.UNKNOWN,
        )
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
                facilities=[facility],
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


def replace_rank(route: Route, rank: int) -> Route:
    return route.model_copy(update={"rank": rank})
