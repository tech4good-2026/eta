from datetime import datetime
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
