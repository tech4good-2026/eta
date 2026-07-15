from app.models import Coordinate, DataSource, PlaceInput
from app.providers.walkway import SyntheticWalkwaySource


def _place(latitude: float, longitude: float) -> PlaceInput:
    return PlaceInput(
        name="p", coordinate=Coordinate(latitude=latitude, longitude=longitude)
    )


def test_synthetic_walkway_is_deterministic_and_marked_synthetic() -> None:
    source = SyntheticWalkwaySource()
    start = _place(37.5, 127.0)
    end = _place(37.51, 127.01)

    first = source.segment_for("leg-1", start, end)
    second = source.segment_for("leg-1", start, end)

    assert first == second
    assert first.source == DataSource.SYNTHETIC_FIXTURE
    assert first.has_stairs is False
    assert first.passable is True
    # 합성 경사는 급경사 하드 차단(6%) 아래에 머문다.
    assert first.max_slope_percent is not None
    assert 0 <= first.max_slope_percent < 6


def test_synthetic_walkway_varies_by_segment() -> None:
    source = SyntheticWalkwaySource()
    start = _place(37.5, 127.0)
    end = _place(37.51, 127.01)

    surfaces = {
        source.segment_for(f"leg-{index}", start, end).surface_type
        for index in range(12)
    }

    assert len(surfaces) > 1
