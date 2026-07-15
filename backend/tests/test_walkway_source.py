import pytest

from app.domain import ProviderLeg, ProviderRoute
from app.models import Coordinate, DataConfidence, DataSource, LegMode, PlaceInput, RouteMode
from app.providers.accessibility import HybridAccessibilityProvider
from app.providers.walkway import MockWalkwaySource, UnknownWalkwaySource


def _place(latitude: float, longitude: float) -> PlaceInput:
    return PlaceInput(
        name="p", coordinate=Coordinate(latitude=latitude, longitude=longitude)
    )


def test_unknown_walkway_source_does_not_invent_data() -> None:
    source = UnknownWalkwaySource()
    start = _place(37.5, 127.0)
    end = _place(37.51, 127.01)

    segment = source.segment_for("leg-1", start, end)

    # 실데이터 미확보 상태에서는 값을 지어내지 않는다.
    assert segment.max_slope_percent is None
    assert segment.surface_type is None
    assert segment.width_m is None
    assert segment.curb_ramp_present is None
    assert segment.tactile_paving_present is None
    assert segment.has_stairs is None
    assert segment.passable is True
    assert segment.confidence == DataConfidence.UNKNOWN
    assert segment.source == DataSource.UNKNOWN


@pytest.mark.asyncio
async def test_accessibility_provider_preserves_unknown_stair_state() -> None:
    start = _place(37.5, 127.0)
    end = _place(37.51, 127.01)
    leg = ProviderLeg(
        provider_leg_id="walk-1",
        mode=LegMode.WALK,
        start=start,
        end=end,
        distance_m=100,
        duration_sec=100,
        geometry=[[127.0, 37.5], [127.01, 37.51]],
    )
    route = ProviderRoute(
        provider_route_id="route-1",
        mode=RouteMode.WALK,
        title="도보",
        standard_duration_sec=100,
        total_distance_m=100,
        walk_distance_m=100,
        transfer_count=0,
        fare_krw=0,
        legs=[leg],
    )

    context = await HybridAccessibilityProvider(
        walkway=UnknownWalkwaySource()
    ).get_context([route])

    assert context.walk["walk-1"].has_stairs is None


def test_mock_walkway_is_deterministic_and_marked_synthetic() -> None:
    source = MockWalkwaySource()
    start = _place(37.5, 127.0)
    end = _place(37.51, 127.01)

    first = source.segment_for("leg-1", start, end)
    second = source.segment_for("leg-1", start, end)

    assert first == second
    assert first.source == DataSource.SYNTHETIC_FIXTURE
    assert first.confidence == DataConfidence.ESTIMATED
    # 목업 경사는 급경사 하드 차단(6%) 아래에 머문다.
    assert first.max_slope_percent is not None
    assert 0 <= first.max_slope_percent < 6
