from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain import (
    AccessibilityContext,
    BusAccessibility,
    ProviderLeg,
    ProviderRoute,
    RealtimeDeparture,
    StationAccessibility,
    WalkAccessibility,
)
from app.main import demo_profile
from app.models import (
    Coordinate,
    DataConfidence,
    DataSource,
    FacilityStatus,
    LegMode,
    LowFloorStatus,
    PlaceInput,
    RouteMode,
    TimeSource,
)
from app.personalization import BaselinePersonalizationEngine

SEOUL = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 7, 15, 14, 0, tzinfo=SEOUL)


def place(name: str, latitude: float, longitude: float) -> PlaceInput:
    return PlaceInput(name=name, coordinate=Coordinate(latitude=latitude, longitude=longitude))


def line(start: PlaceInput, end: PlaceInput) -> list[list[float]]:
    return [
        [start.coordinate.longitude, start.coordinate.latitude],
        [end.coordinate.longitude, end.coordinate.latitude],
    ]


def test_recalculates_walk_time_from_profile_speed() -> None:
    origin = place("서울역", 37.5547, 126.9707)
    destination = place("시청", 37.5663, 126.9779)
    candidate = ProviderRoute(
        provider_route_id="walk-1",
        mode=RouteMode.WALK,
        title="도보 경로",
        standard_duration_sec=900,
        total_distance_m=800,
        walk_distance_m=800,
        transfer_count=0,
        fare_krw=0,
        legs=[
            ProviderLeg(
                provider_leg_id="walk-leg-1",
                mode=LegMode.WALK,
                start=origin,
                end=destination,
                distance_m=800,
                duration_sec=900,
                geometry=line(origin, destination),
            )
        ],
    )
    context = AccessibilityContext(
        walk={
            "walk-leg-1": WalkAccessibility(
                has_stairs=False,
                max_slope_percent=2.0,
                confidence=DataConfidence.ESTIMATED,
            )
        }
    )

    [route] = BaselinePersonalizationEngine().personalize_routes(
        [candidate], demo_profile(), context, NOW
    )

    assert route.legs[0].personalized_duration_sec == 1000
    assert route.summary.personalized_duration_sec == 1000
    assert route.summary.arrival_at == datetime(2026, 7, 15, 14, 16, 40, tzinfo=SEOUL)
    assert route.accessibility_status == "ACCESSIBLE"


def test_marks_explicitly_inaccessible_transit_route_unavailable() -> None:
    origin = place("정류장 A", 37.5, 127.0)
    destination = place("정류장 B", 37.51, 127.01)
    candidate = ProviderRoute(
        provider_route_id="bus-1",
        mode=RouteMode.TRANSIT,
        title="일반버스 경로",
        standard_duration_sec=600,
        total_distance_m=3000,
        walk_distance_m=0,
        transfer_count=0,
        fare_krw=1500,
        legs=[
            ProviderLeg(
                provider_leg_id="bus-leg-1",
                mode=LegMode.BUS,
                start=origin,
                end=destination,
                distance_m=3000,
                duration_sec=600,
                geometry=line(origin, destination),
                route_id="100",
                route_name="100번",
                departure_at=NOW,
                arrival_at=datetime(2026, 7, 15, 14, 10, tzinfo=SEOUL),
            )
        ],
    )
    context = AccessibilityContext(
        bus={
            "bus-leg-1": BusAccessibility(
                low_floor_status=LowFloorStatus.NOT_LOW_FLOOR,
                confidence=DataConfidence.VERIFIED,
            )
        }
    )

    [route] = BaselinePersonalizationEngine().personalize_routes(
        [candidate], demo_profile(), context, NOW
    )

    assert route.accessibility_status == "UNAVAILABLE"
    assert route.unavailable_reasons[0].code == "LOW_FLOOR_BUS_REQUIRED"


def test_selects_catchable_low_floor_bus_and_includes_realtime_wait_in_eta() -> None:
    origin = place("출발지", 37.56, 127.00)
    boarding = place("동대문역사문화공원역8번출구", 37.565033, 127.007283)
    destination = place("잠실역", 37.5133, 127.1002)
    candidate = ProviderRoute(
        provider_route_id="realtime-bus",
        mode=RouteMode.TRANSIT,
        title="301번",
        standard_duration_sec=780,
        total_distance_m=5240,
        walk_distance_m=240,
        transfer_count=0,
        fare_krw=1500,
        legs=[
            ProviderLeg(
                provider_leg_id="walk-to-bus",
                mode=LegMode.WALK,
                start=origin,
                end=boarding,
                distance_m=240,
                duration_sec=180,
                geometry=line(origin, boarding),
            ),
            ProviderLeg(
                provider_leg_id="bus-301",
                mode=LegMode.BUS,
                start=boarding,
                end=destination,
                distance_m=5000,
                duration_sec=600,
                geometry=line(boarding, destination),
                route_id="tmap-301",
                route_name="간선:301",
                departure_at=datetime(2026, 7, 15, 14, 3, tzinfo=SEOUL),
                arrival_at=datetime(2026, 7, 15, 14, 13, tzinfo=SEOUL),
                time_source=TimeSource.SCHEDULED,
            ),
        ],
    )
    context = AccessibilityContext(
        walk={
            "walk-to-bus": WalkAccessibility(
                has_stairs=False,
                max_slope_percent=2,
                confidence=DataConfidence.VERIFIED,
            )
        },
        bus={
            "bus-301": BusAccessibility(
                low_floor_status=LowFloorStatus.CONFIRMED,
                confidence=DataConfidence.VERIFIED,
                source=DataSource.SEOUL_OPEN_DATA,
                departures=(
                    RealtimeDeparture(
                        departure_at=datetime(2026, 7, 15, 14, 2, tzinfo=SEOUL),
                        low_floor_status=LowFloorStatus.NOT_LOW_FLOOR,
                        vehicle_id="normal-bus",
                    ),
                    RealtimeDeparture(
                        departure_at=datetime(2026, 7, 15, 14, 8, tzinfo=SEOUL),
                        low_floor_status=LowFloorStatus.CONFIRMED,
                        vehicle_id="low-floor-bus",
                    ),
                ),
            )
        },
    )

    [route] = BaselinePersonalizationEngine().personalize_routes(
        [candidate], demo_profile(), context, NOW
    )

    bus_leg = route.legs[1]
    assert bus_leg.low_floor_status == LowFloorStatus.CONFIRMED
    assert bus_leg.departure_at == datetime(2026, 7, 15, 14, 8, tzinfo=SEOUL)
    assert bus_leg.arrival_at == datetime(2026, 7, 15, 14, 18, tzinfo=SEOUL)
    assert bus_leg.time_source == TimeSource.REALTIME
    assert route.summary.personalized_duration_sec == 1080
    assert route.summary.arrival_at == datetime(2026, 7, 15, 14, 18, tzinfo=SEOUL)


def test_personalized_walk_time_never_becomes_shorter_than_provider_time() -> None:
    origin = place("출발", 37.5, 127.0)
    destination = place("도착", 37.51, 127.01)
    candidate = ProviderRoute(
        provider_route_id="slow-provider-walk",
        mode=RouteMode.WALK,
        title="혼잡한 보행 경로",
        standard_duration_sec=1200,
        total_distance_m=800,
        walk_distance_m=800,
        transfer_count=0,
        fare_krw=0,
        legs=[
            ProviderLeg(
                provider_leg_id="slow-walk-leg",
                mode=LegMode.WALK,
                start=origin,
                end=destination,
                distance_m=800,
                duration_sec=1200,
                geometry=line(origin, destination),
            )
        ],
    )
    context = AccessibilityContext(
        walk={
            "slow-walk-leg": WalkAccessibility(
                has_stairs=False,
                max_slope_percent=2,
                confidence=DataConfidence.VERIFIED,
            )
        }
    )

    [route] = BaselinePersonalizationEngine().personalize_routes(
        [candidate], demo_profile(), context, NOW
    )

    assert route.legs[0].personalized_duration_sec == 1200
    assert route.summary.personalized_duration_sec == 1200


def test_unknown_elevator_data_is_caution_not_false_unavailable() -> None:
    origin = place("서울역", 37.5547, 126.9707)
    destination = place("시청역", 37.5657, 126.9770)
    candidate = ProviderRoute(
        provider_route_id="subway-1",
        mode=RouteMode.TRANSIT,
        title="1호선",
        standard_duration_sec=120,
        total_distance_m=1000,
        walk_distance_m=0,
        transfer_count=0,
        fare_krw=1500,
        legs=[
            ProviderLeg(
                provider_leg_id="subway-leg-1",
                mode=LegMode.SUBWAY,
                start=origin,
                end=destination,
                distance_m=1000,
                duration_sec=120,
                geometry=line(origin, destination),
                line_id="SUBWAY_LINE_1",
                line_name="1호선",
                departure_at=NOW,
                arrival_at=datetime(2026, 7, 15, 14, 2, tzinfo=SEOUL),
            )
        ],
    )
    context = AccessibilityContext(
        subway={
            "subway-leg-1": StationAccessibility(
                elevator_status=None,
                confidence=DataConfidence.UNKNOWN,
            )
        }
    )

    [route] = BaselinePersonalizationEngine().personalize_routes(
        [candidate], demo_profile(), context, NOW
    )

    assert route.accessibility_status == "CAUTION"
    assert route.warnings[0].code == "ELEVATOR_STATUS_UNKNOWN"


def test_realtime_subway_skips_train_without_accessible_boarding_buffer() -> None:
    origin = place("출발지", 37.55, 126.97)
    boarding = place("서울역", 37.5547, 126.9707)
    destination = place("사당역", 37.4768, 126.9816)
    candidate = ProviderRoute(
        provider_route_id="realtime-subway",
        mode=RouteMode.TRANSIT,
        title="4호선",
        standard_duration_sec=700,
        total_distance_m=5100,
        walk_distance_m=100,
        transfer_count=0,
        fare_krw=1500,
        legs=[
            ProviderLeg(
                provider_leg_id="walk-to-subway",
                mode=LegMode.WALK,
                start=origin,
                end=boarding,
                distance_m=100,
                duration_sec=100,
                geometry=line(origin, boarding),
            ),
            ProviderLeg(
                provider_leg_id="subway-4",
                mode=LegMode.SUBWAY,
                start=boarding,
                end=destination,
                distance_m=5000,
                duration_sec=600,
                geometry=line(boarding, destination),
                line_id="tmap-line-4",
                line_name="수도권4호선",
                departure_at=datetime(2026, 7, 15, 14, 2, tzinfo=SEOUL),
                arrival_at=datetime(2026, 7, 15, 14, 12, tzinfo=SEOUL),
                time_source=TimeSource.SCHEDULED,
            ),
        ],
    )
    context = AccessibilityContext(
        walk={
            "walk-to-subway": WalkAccessibility(
                has_stairs=False,
                max_slope_percent=2,
                confidence=DataConfidence.VERIFIED,
            )
        },
        subway={
            "subway-4": StationAccessibility(
                elevator_status=FacilityStatus.AVAILABLE,
                confidence=DataConfidence.VERIFIED,
                source=DataSource.SEOUL_OPEN_DATA,
                departures=(
                    RealtimeDeparture(
                        departure_at=datetime(2026, 7, 15, 14, 2, 30, tzinfo=SEOUL),
                        direction="오이도행",
                    ),
                    RealtimeDeparture(
                        departure_at=datetime(2026, 7, 15, 14, 4, tzinfo=SEOUL),
                        direction="오이도행",
                    ),
                ),
            )
        },
    )

    [route] = BaselinePersonalizationEngine().personalize_routes(
        [candidate], demo_profile(), context, NOW
    )

    subway_leg = route.legs[1]
    assert subway_leg.departure_at == datetime(2026, 7, 15, 14, 4, tzinfo=SEOUL)
    assert subway_leg.arrival_at == datetime(2026, 7, 15, 14, 14, tzinfo=SEOUL)
    assert subway_leg.time_source == TimeSource.REALTIME
    assert route.summary.personalized_duration_sec == 840


def test_sorts_accessible_before_caution_before_unavailable() -> None:
    origin = place("출발", 37.5, 127.0)
    destination = place("도착", 37.51, 127.01)

    def walk_candidate(candidate_id: str) -> ProviderRoute:
        return ProviderRoute(
            provider_route_id=candidate_id,
            mode=RouteMode.WALK,
            title=candidate_id,
            standard_duration_sec=100,
            total_distance_m=80,
            walk_distance_m=80,
            transfer_count=0,
            fare_krw=0,
            legs=[
                ProviderLeg(
                    provider_leg_id=candidate_id,
                    mode=LegMode.WALK,
                    start=origin,
                    end=destination,
                    distance_m=80,
                    duration_sec=100,
                    geometry=line(origin, destination),
                )
            ],
        )

    candidates = [walk_candidate("unknown"), walk_candidate("stairs"), walk_candidate("safe")]
    context = AccessibilityContext(
        walk={
            "unknown": WalkAccessibility(),
            "stairs": WalkAccessibility(has_stairs=True, confidence=DataConfidence.VERIFIED),
            "safe": WalkAccessibility(
                has_stairs=False,
                max_slope_percent=2.0,
                confidence=DataConfidence.VERIFIED,
            ),
        }
    )

    routes = BaselinePersonalizationEngine().personalize_routes(
        candidates, demo_profile(), context, NOW
    )

    assert [route.accessibility_status for route in routes] == [
        "ACCESSIBLE",
        "CAUTION",
        "UNAVAILABLE",
    ]
    assert [route.rank for route in routes] == [1, 2, 3]


def _walk_only_candidate(distance_m: int = 800, duration_sec: int = 600) -> ProviderRoute:
    origin = place("A", 37.50, 127.00)
    destination = place("B", 37.51, 127.01)
    return ProviderRoute(
        provider_route_id="walk-env",
        mode=RouteMode.WALK,
        title="도보 경로",
        standard_duration_sec=duration_sec,
        total_distance_m=distance_m,
        walk_distance_m=distance_m,
        transfer_count=0,
        fare_krw=0,
        legs=[
            ProviderLeg(
                provider_leg_id="walk-env-1",
                mode=LegMode.WALK,
                start=origin,
                end=destination,
                distance_m=distance_m,
                duration_sec=duration_sec,
                geometry=line(origin, destination),
            )
        ],
    )


def _walk_context(**kwargs) -> AccessibilityContext:
    return AccessibilityContext(
        walk={"walk-env-1": WalkAccessibility(confidence=DataConfidence.ESTIMATED, **kwargs)}
    )


def test_rough_surface_adds_walk_time_for_wheelchair_user() -> None:
    from app.models import SurfaceType

    [route] = BaselinePersonalizationEngine().personalize_routes(
        [_walk_only_candidate()],
        demo_profile(),
        _walk_context(surface_type=SurfaceType.STONE),
        NOW,
    )

    # base ceil(800/0.8)=1000, 바퀴형 거친 노면 패널티 0.30 → 1300
    assert route.legs[0].personalized_duration_sec == 1300
    assert any(warning.code == "ROUGH_SURFACE" for warning in route.warnings)


def test_missing_curb_ramp_heavily_penalizes_wheelchair_user() -> None:
    [route] = BaselinePersonalizationEngine().personalize_routes(
        [_walk_only_candidate()],
        demo_profile(),
        _walk_context(curb_ramp_present=False),
        NOW,
    )

    # 턱낮춤 미비 패널티 1.50 → ceil(1000*2.5)=2500
    assert route.legs[0].personalized_duration_sec == 2500
    assert any(warning.code == "MISSING_CURB_RAMP" for warning in route.warnings)
    assert route.accessibility_status == "CAUTION"


def test_impassable_walkway_makes_route_unavailable() -> None:
    [route] = BaselinePersonalizationEngine().personalize_routes(
        [_walk_only_candidate()],
        demo_profile(),
        _walk_context(passable=False),
        NOW,
    )

    assert route.accessibility_status == "UNAVAILABLE"
    assert any(
        reason.code == "WALKWAY_BLOCKED" for reason in route.unavailable_reasons
    )


def test_slope_penalty_is_larger_for_wheeled_aids() -> None:
    engine = BaselinePersonalizationEngine()
    wheeled_profile = demo_profile()
    unaided_profile = demo_profile().model_copy(
        update={"mobility_aids": []}, deep=True
    )

    [wheeled] = engine.personalize_routes(
        [_walk_only_candidate()], wheeled_profile, _walk_context(max_slope_percent=5.0), NOW
    )
    [unaided] = engine.personalize_routes(
        [_walk_only_candidate()], unaided_profile, _walk_context(max_slope_percent=5.0), NOW
    )

    assert (
        wheeled.legs[0].personalized_duration_sec
        > unaided.legs[0].personalized_duration_sec
    )
