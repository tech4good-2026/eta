from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain import AccessibilityContext, ProviderLeg, ProviderRoute
from app.main import demo_profile
from app.models import Coordinate, LegMode, PlaceInput, RouteMode, RouteSearchRequest
from app.personalization import BaselinePersonalizationEngine
from app.services import RouteService, StoredRoute
from app.storage import MemoryTTLStore

SEOUL = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 7, 16, 14, 0, tzinfo=SEOUL)

ORIGIN = PlaceInput(name="출발", coordinate=Coordinate(latitude=37.50, longitude=127.00))
DEST = PlaceInput(name="도착", coordinate=Coordinate(latitude=37.51, longitude=127.01))
STOP = PlaceInput(name="정류장", coordinate=Coordinate(latitude=37.502, longitude=127.002))


def _line(start: PlaceInput, end: PlaceInput) -> list[list[float]]:
    return [
        [start.coordinate.longitude, start.coordinate.latitude],
        [end.coordinate.longitude, end.coordinate.latitude],
    ]


def _transit_candidate(bus_wait_min: int) -> ProviderRoute:
    departure = NOW + timedelta(minutes=bus_wait_min)
    return ProviderRoute(
        provider_route_id="transit-1",
        mode=RouteMode.TRANSIT,
        title="버스 경로",
        standard_duration_sec=bus_wait_min * 60 + 700,
        total_distance_m=3100,
        walk_distance_m=100,
        transfer_count=0,
        fare_krw=1500,
        legs=[
            ProviderLeg(
                provider_leg_id="walk-1",
                mode=LegMode.WALK,
                start=ORIGIN,
                end=STOP,
                distance_m=80,
                duration_sec=100,
                geometry=_line(ORIGIN, STOP),
            ),
            ProviderLeg(
                provider_leg_id="bus-1",
                mode=LegMode.BUS,
                start=STOP,
                end=DEST,
                distance_m=3000,
                duration_sec=600,
                geometry=_line(STOP, DEST),
                route_id="770",
                route_name="770번",
                departure_at=departure,
                arrival_at=departure + timedelta(seconds=600),
            ),
        ],
    )


def _taxi_candidate(duration_sec: int) -> ProviderRoute:
    return ProviderRoute(
        provider_route_id="taxi-1",
        mode=RouteMode.TAXI,
        title="택시 경로",
        standard_duration_sec=duration_sec,
        total_distance_m=3500,
        walk_distance_m=0,
        transfer_count=0,
        fare_krw=8000,
        legs=[
            ProviderLeg(
                provider_leg_id="taxi-leg-1",
                mode=LegMode.TAXI,
                start=ORIGIN,
                end=DEST,
                distance_m=3500,
                duration_sec=duration_sec,
                geometry=_line(ORIGIN, DEST),
                expected_fare_krw=8000,
            )
        ],
    )


class StubProvider:
    def __init__(self, transit: ProviderRoute, taxi: ProviderRoute) -> None:
        self.transit = transit
        self.taxi = taxi

    async def search(self, request: RouteSearchRequest) -> list[ProviderRoute]:
        if request.mode == RouteMode.TRANSIT:
            return [self.transit]
        return [self.taxi]


class EmptyAccessibility:
    async def get_context(self, routes) -> AccessibilityContext:
        return AccessibilityContext()


def _service(bus_wait_min: int, taxi_sec: int) -> RouteService:
    return RouteService(
        provider=StubProvider(_transit_candidate(bus_wait_min), _taxi_candidate(taxi_sec)),
        accessibility=EmptyAccessibility(),
        engine=BaselinePersonalizationEngine(),
        store=MemoryTTLStore[StoredRoute](clock=lambda: NOW),
        provider_cache=MemoryTTLStore(clock=lambda: NOW),
        clock=lambda: NOW,
    )


def _request() -> RouteSearchRequest:
    return RouteSearchRequest(
        origin=ORIGIN, destination=DEST, mode=RouteMode.TRANSIT, departure_at=NOW
    )


@pytest.mark.asyncio
async def test_recommends_call_taxi_when_bus_wait_is_long_and_taxi_is_faster() -> None:
    response = await _service(bus_wait_min=20, taxi_sec=900).search(
        _request(), demo_profile()
    )

    codes = [notice.code for notice in response.notices]
    assert "CALL_TAXI_RECOMMENDED" in codes
    assert "TAXI" in [str(mode) for mode in response.fallback_modes]
    assert any(
        warning.code == "CALL_TAXI_RECOMMENDED"
        for route in response.routes
        for warning in route.warnings
    )


@pytest.mark.asyncio
async def test_hybrid_transit_taxi_route_is_added_when_faster() -> None:
    response = await _service(bus_wait_min=20, taxi_sec=900).search(
        _request(), demo_profile()
    )

    assert len(response.routes) == 2
    hybrid = response.routes[0]
    # 결합 경로가 더 빨라 1위가 된다: 도보 접근 + 콜택시.
    assert "콜택시" in hybrid.title
    assert [leg.mode for leg in hybrid.legs] == ["WALK", "TAXI"]
    assert any(warning.code == "HYBRID_CALL_TAXI" for warning in hybrid.warnings)
    assert (
        hybrid.summary.personalized_duration_sec
        < response.routes[1].summary.personalized_duration_sec
    )


@pytest.mark.asyncio
async def test_hybrid_route_is_not_added_when_transit_is_faster() -> None:
    response = await _service(bus_wait_min=3, taxi_sec=900).search(
        _request(), demo_profile()
    )

    assert len(response.routes) == 1
    assert not any("콜택시" in route.title for route in response.routes)


@pytest.mark.asyncio
async def test_no_call_taxi_recommendation_when_bus_wait_is_short() -> None:
    response = await _service(bus_wait_min=3, taxi_sec=900).search(
        _request(), demo_profile()
    )

    codes = [notice.code for notice in response.notices]
    assert "CALL_TAXI_RECOMMENDED" not in codes


@pytest.mark.asyncio
async def test_no_call_taxi_recommendation_when_taxi_is_slower() -> None:
    response = await _service(bus_wait_min=20, taxi_sec=7200).search(
        _request(), demo_profile()
    )

    codes = [notice.code for notice in response.notices]
    assert "CALL_TAXI_RECOMMENDED" not in codes
