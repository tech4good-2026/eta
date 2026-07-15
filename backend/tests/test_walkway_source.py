from app.models import Coordinate, DataConfidence, DataSource, PlaceInput
from app.providers.walkway import UnknownWalkwaySource


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
