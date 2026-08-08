import asyncio
from datetime import datetime
from time import monotonic
from zoneinfo import ZoneInfo

import pytest

from app.domain import ProviderLeg, ProviderRoute
from app.models import (
    Coordinate,
    DataConfidence,
    DataSource,
    FacilityStatus,
    LegMode,
    LowFloorStatus,
    PlaceInput,
    RouteMode,
)
from app.providers.accessibility import HybridAccessibilityProvider
from app.providers.seoul import SeoulElevator, SeoulSubwayArrival
from app.providers.seoul_bus import SeoulBusArrival


class PartialElevatorClient:
    async def get_elevator(self, station_name: str):
        if station_name == "탑승역":
            return SeoulElevator(
                status=FacilityStatus.AVAILABLE,
                location_description="1번 출구",
                confidence=DataConfidence.VERIFIED,
            )
        return None


class RealtimeSeoulClient:
    async def get_elevator(self, _station_name: str):
        return SeoulElevator(
            status=FacilityStatus.AVAILABLE,
            location_description="엘리베이터",
            confidence=DataConfidence.VERIFIED,
        )

    async def get_subway_arrivals(self, _station_name: str, _line_name: str):
        return [
            SeoulSubwayArrival(
                arrival_sec=45,
                train_id="K401",
                direction="진접행 - 상행",
                terminal_station="진접",
            ),
            SeoulSubwayArrival(
                arrival_sec=180,
                train_id="K402",
                direction="오이도행 - 하행",
                terminal_station="오이도",
            ),
        ]


class RealtimeBusClient:
    async def get_arrivals(self, _route_name: str, _boarding_stop: PlaceInput):
        return [
            SeoulBusArrival(
                arrival_sec=120,
                low_floor_status=LowFloorStatus.NOT_LOW_FLOOR,
                vehicle_id="normal-bus",
            ),
            SeoulBusArrival(
                arrival_sec=480,
                low_floor_status=LowFloorStatus.CONFIRMED,
                vehicle_id="low-floor-bus",
            ),
        ]


@pytest.mark.asyncio
async def test_subway_requires_elevator_data_for_both_boarding_and_alighting_station() -> None:
    start = PlaceInput(
        name="탑승역",
        coordinate=Coordinate(latitude=37.5, longitude=127.0),
    )
    end = PlaceInput(
        name="하차역",
        coordinate=Coordinate(latitude=37.51, longitude=127.01),
    )
    route = ProviderRoute(
        provider_route_id="subway-route",
        mode=RouteMode.TRANSIT,
        title="지하철 경로",
        standard_duration_sec=600,
        total_distance_m=3000,
        walk_distance_m=0,
        transfer_count=0,
        fare_krw=1500,
        legs=[
            ProviderLeg(
                provider_leg_id="subway-leg",
                mode=LegMode.SUBWAY,
                start=start,
                end=end,
                distance_m=3000,
                duration_sec=600,
                geometry=[[127.0, 37.5], [127.01, 37.51]],
                line_id="SUBWAY_LINE_1",
                line_name="1호선",
                departure_at=datetime(2026, 7, 15, 14, 0, tzinfo=ZoneInfo("Asia/Seoul")),
                arrival_at=datetime(2026, 7, 15, 14, 10, tzinfo=ZoneInfo("Asia/Seoul")),
            )
        ],
    )

    context = await HybridAccessibilityProvider(PartialElevatorClient()).get_context([route])
    subway = context.subway["subway-leg"]

    assert subway.elevator_status == FacilityStatus.UNKNOWN
    assert subway.confidence == DataConfidence.UNKNOWN
    assert subway.source == DataSource.SEOUL_OPEN_DATA


@pytest.mark.asyncio
async def test_bus_and_subway_realtime_arrivals_are_combined_into_context() -> None:
    now = datetime(2026, 7, 15, 14, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    bus_start = PlaceInput(
        name="동대문역사문화공원역8번출구",
        coordinate=Coordinate(latitude=37.565033, longitude=127.007283),
    )
    transfer = PlaceInput(
        name="잠실역",
        coordinate=Coordinate(latitude=37.5133, longitude=127.1002),
    )
    destination = PlaceInput(
        name="강남역",
        coordinate=Coordinate(latitude=37.4979, longitude=127.0276),
    )
    route = ProviderRoute(
        provider_route_id="realtime-route",
        mode=RouteMode.TRANSIT,
        title="301 → 2호선",
        standard_duration_sec=1200,
        total_distance_m=8000,
        walk_distance_m=0,
        transfer_count=1,
        fare_krw=1500,
        legs=[
            ProviderLeg(
                provider_leg_id="bus-leg",
                mode=LegMode.BUS,
                start=bus_start,
                end=transfer,
                distance_m=5000,
                duration_sec=600,
                geometry=[[127.007283, 37.565033], [127.1002, 37.5133]],
                route_id="tmap-301",
                route_name="간선:301",
            ),
            ProviderLeg(
                provider_leg_id="subway-leg",
                mode=LegMode.SUBWAY,
                start=transfer,
                end=destination,
                distance_m=3000,
                duration_sec=600,
                geometry=[[127.1002, 37.5133], [127.0276, 37.4979]],
                line_id="tmap-line-2",
                line_name="수도권2호선",
            ),
        ],
    )

    context = await HybridAccessibilityProvider(
        seoul=RealtimeSeoulClient(),
        bus=RealtimeBusClient(),
        clock=lambda: now,
    ).get_context([route])

    assert [value.departure_at for value in context.bus["bus-leg"].departures] == [
        datetime(2026, 7, 15, 14, 2, tzinfo=ZoneInfo("Asia/Seoul")),
        datetime(2026, 7, 15, 14, 8, tzinfo=ZoneInfo("Asia/Seoul")),
    ]
    assert context.bus["bus-leg"].departures[1].low_floor_status == LowFloorStatus.CONFIRMED
    assert context.bus["bus-leg"].source == DataSource.SEOUL_OPEN_DATA
    assert [
        value.departure_at for value in context.subway["subway-leg"].departures
    ] == [
        datetime(2026, 7, 15, 14, 0, 45, tzinfo=ZoneInfo("Asia/Seoul")),
        datetime(2026, 7, 15, 14, 3, tzinfo=ZoneInfo("Asia/Seoul")),
    ]


@pytest.mark.asyncio
async def test_live_mode_without_bus_key_does_not_claim_synthetic_low_floor_bus() -> None:
    start = PlaceInput(
        name="버스 정류장",
        coordinate=Coordinate(latitude=37.5, longitude=127.0),
    )
    end = PlaceInput(
        name="도착 정류장",
        coordinate=Coordinate(latitude=37.51, longitude=127.01),
    )
    route = ProviderRoute(
        provider_route_id="bus-route",
        mode=RouteMode.TRANSIT,
        title="301번",
        standard_duration_sec=600,
        total_distance_m=3000,
        walk_distance_m=0,
        transfer_count=0,
        fare_krw=1500,
        legs=[
            ProviderLeg(
                provider_leg_id="bus-leg",
                mode=LegMode.BUS,
                start=start,
                end=end,
                distance_m=3000,
                duration_sec=600,
                geometry=[[127.0, 37.5], [127.01, 37.51]],
                route_id="tmap-301",
                route_name="간선:301",
            )
        ],
    )

    context = await HybridAccessibilityProvider(
        bus=None,
        use_synthetic_bus=False,
    ).get_context([route])

    assert context.bus["bus-leg"].low_floor_status == LowFloorStatus.UNKNOWN
    assert context.bus["bus-leg"].confidence == DataConfidence.UNKNOWN
    assert context.bus["bus-leg"].source == DataSource.UNKNOWN


# ── 여기서부터: 외부를 "차례로" 묻지 않는다는 것을 고정한다 ──────────────────
#
# 구간끼리는 서로 필요로 하는 게 없다. 그런데도 차례로 기다리면 응답 시간이
# 호출들의 합이 된다. 아래 세 가지가 그 성질을 지킨다.


def _station(name: str, lat: float, lon: float) -> PlaceInput:
    return PlaceInput(name=name, coordinate=Coordinate(latitude=lat, longitude=lon))


def _subway_leg(leg_id: str, start: PlaceInput, end: PlaceInput) -> ProviderLeg:
    return ProviderLeg(
        provider_leg_id=leg_id,
        mode=LegMode.SUBWAY,
        start=start,
        end=end,
        distance_m=3000,
        duration_sec=600,
        geometry=[[start.coordinate.longitude, start.coordinate.latitude],
                  [end.coordinate.longitude, end.coordinate.latitude]],
        line_id="SUBWAY_LINE_1",
        line_name="1호선",
        departure_at=datetime(2026, 7, 15, 14, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        arrival_at=datetime(2026, 7, 15, 14, 10, tzinfo=ZoneInfo("Asia/Seoul")),
    )


def _route(route_id: str, legs: list[ProviderLeg]) -> ProviderRoute:
    return ProviderRoute(
        provider_route_id=route_id,
        mode=RouteMode.TRANSIT,
        title="지하철 경로",
        standard_duration_sec=600,
        total_distance_m=3000,
        walk_distance_m=0,
        transfer_count=max(0, len(legs) - 1),
        fare_krw=1500,
        legs=legs,
    )


class SlowSeoulClient:
    """호출 하나마다 정해진 시간을 쓰고, 몇 번 불렸는지 센다."""

    def __init__(self, delay_sec: float) -> None:
        self.delay_sec = delay_sec
        self.elevator_calls: list[str] = []
        self.arrival_calls: list[str] = []

    async def get_elevator(self, station_name: str):
        self.elevator_calls.append(station_name)
        await asyncio.sleep(self.delay_sec)
        return SeoulElevator(
            status=FacilityStatus.AVAILABLE,
            location_description="엘리베이터",
            confidence=DataConfidence.VERIFIED,
        )

    async def get_subway_arrivals(self, station_name: str, _line_name: str):
        self.arrival_calls.append(station_name)
        await asyncio.sleep(self.delay_sec)
        return []


@pytest.mark.asyncio
async def test_legs_are_asked_together_so_latency_does_not_add_up() -> None:
    """구간 4개짜리 경로. 차례로 물으면 지연이 쌓이고, 같이 물으면 안 쌓인다."""
    delay = 0.05
    seoul = SlowSeoulClient(delay)
    legs = [
        _subway_leg(
            f"leg-{i}",
            _station(f"역{i}", 37.5 + i / 100, 127.0 + i / 100),
            _station(f"역{i + 1}", 37.5 + (i + 1) / 100, 127.0 + (i + 1) / 100),
        )
        for i in range(4)
    ]

    started = monotonic()
    context = await HybridAccessibilityProvider(seoul).get_context([_route("r", legs)])
    elapsed = monotonic() - started

    assert len(context.subway) == 4
    # 구간 4개 × 구간당 독립 호출 5개 = 차례로면 20단계(1.0초 이상).
    # 같이 물으면 한 단계로 끝난다. 넉넉히 잡아도 절반을 넘지 않아야 한다.
    assert elapsed < delay * 10, f"{elapsed:.3f}s — 아직 차례로 기다리고 있다"


@pytest.mark.asyncio
async def test_same_station_shared_by_route_candidates_is_asked_once() -> None:
    """경로 후보가 여러 개여도 같은 구간을 두 번 묻지 않는다."""
    seoul = SlowSeoulClient(0.0)
    start, end = _station("탑승역", 37.5, 127.0), _station("하차역", 37.51, 127.01)
    routes = [
        _route("candidate-1", [_subway_leg("a", start, end)]),
        _route("candidate-2", [_subway_leg("b", start, end)]),
        _route("candidate-3", [_subway_leg("c", start, end)]),
    ]

    context = await HybridAccessibilityProvider(seoul).get_context(routes)

    assert len(context.subway) == 3, "구간마다 답은 다 채워져야 한다"
    assert seoul.arrival_calls == ["탑승역"], "같은 구간을 세 번 물었다"
    assert sorted(set(seoul.elevator_calls)) == ["탑승역", "하차역"]
    assert len(seoul.elevator_calls) == 2, "같은 역을 여러 번 물었다"


class HangingSeoulClient:
    """영영 답하지 않는 외부. 실제로 종종 이렇게 된다."""

    async def get_elevator(self, _station_name: str):
        await asyncio.sleep(3600)

    async def get_subway_arrivals(self, _station_name: str, _line_name: str):
        await asyncio.sleep(3600)


@pytest.mark.asyncio
async def test_slow_provider_degrades_to_unknown_instead_of_blocking() -> None:
    """늦은 것과 못 받은 것을 같게 다룬다 — 둘 다 '확인 안 됨'이다."""
    start, end = _station("탑승역", 37.5, 127.0), _station("하차역", 37.51, 127.01)
    route = _route("r", [_subway_leg("subway-leg", start, end)])

    started = monotonic()
    context = await HybridAccessibilityProvider(
        HangingSeoulClient(), provider_timeout_sec=0.05
    ).get_context([route])
    elapsed = monotonic() - started

    subway = context.subway["subway-leg"]
    assert subway.elevator_status == FacilityStatus.UNKNOWN
    assert subway.confidence == DataConfidence.UNKNOWN
    assert elapsed < 1.0, f"{elapsed:.3f}s — 응답이 외부에 붙들렸다"
