from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain import AccessibilityContext, BusAccessibility, ProviderLeg, ProviderRoute
from app.main import demo_profile
from app.models import (
    Coordinate,
    DataConfidence,
    LegMode,
    LowFloorStatus,
    PlaceInput,
    RouteMode,
    RouteSearchRequest,
)
from app.personalization import BaselinePersonalizationEngine
from app.services import RouteService, StoredRoute
from app.storage import MemoryTTLStore

SEOUL = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 7, 15, 14, 0, tzinfo=SEOUL)


class BusOnlyProvider:
    async def search(self, request: RouteSearchRequest) -> list[ProviderRoute]:
        leg = ProviderLeg(
            provider_leg_id="ordinary-bus",
            mode=LegMode.BUS,
            start=request.origin,
            end=request.destination,
            distance_m=3000,
            duration_sec=600,
            geometry=[
                [request.origin.coordinate.longitude, request.origin.coordinate.latitude],
                [request.destination.coordinate.longitude, request.destination.coordinate.latitude],
            ],
            route_id="100",
            route_name="100번",
            departure_at=NOW,
            arrival_at=datetime(2026, 7, 15, 14, 10, tzinfo=SEOUL),
        )
        return [
            ProviderRoute(
                provider_route_id="ordinary-bus-route",
                mode=RouteMode.TRANSIT,
                title="일반버스 경로",
                standard_duration_sec=600,
                total_distance_m=3000,
                walk_distance_m=0,
                transfer_count=0,
                fare_krw=1500,
                legs=[leg],
            )
        ]


class NoLowFloorContext:
    async def get_context(self, routes: list[ProviderRoute]) -> AccessibilityContext:
        return AccessibilityContext(
            bus={
                "ordinary-bus": BusAccessibility(
                    low_floor_status=LowFloorStatus.NOT_LOW_FLOOR,
                    confidence=DataConfidence.VERIFIED,
                )
            }
        )


@pytest.mark.asyncio
async def test_no_accessible_transit_route_is_200_style_result_with_taxi_fallback() -> None:
    service = RouteService(
        provider=BusOnlyProvider(),
        accessibility=NoLowFloorContext(),
        engine=BaselinePersonalizationEngine(),
        store=MemoryTTLStore[StoredRoute](clock=lambda: NOW),
        clock=lambda: NOW,
    )
    request = RouteSearchRequest(
        origin=PlaceInput(
            name="출발",
            coordinate=Coordinate(latitude=37.5, longitude=127.0),
        ),
        destination=PlaceInput(
            name="도착",
            coordinate=Coordinate(latitude=37.51, longitude=127.01),
        ),
        mode=RouteMode.TRANSIT,
        departure_at=NOW,
    )

    result = await service.search(request, demo_profile())

    assert result.status == "NO_ACCESSIBLE_ROUTE"
    assert result.routes == []
    assert result.fallback_modes == ["TAXI"]
    assert result.notices[0].code == "LOW_FLOOR_BUS_UNAVAILABLE"
