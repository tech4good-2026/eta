import asyncio

import httpx
import pytest

from app.config import Settings
from app.domain import ProviderLeg, ProviderRoute
from app.errors import ApiError
from app.main import build_container
from app.models import Coordinate, DataConfidence, DataSource, FacilityStatus, LegMode, PlaceInput, RouteMode
from app.providers.seoul import SeoulDataClient


def route() -> ProviderRoute:
    start = PlaceInput(name="서울역", coordinate=Coordinate(latitude=37.55, longitude=126.97))
    end = PlaceInput(name="시청역", coordinate=Coordinate(latitude=37.56, longitude=126.98))
    return ProviderRoute(provider_route_id="r", mode=RouteMode.TRANSIT, title="검증", standard_duration_sec=600,
        total_distance_m=1000, walk_distance_m=100, transfer_count=0, fare_krw=1500,
        legs=[ProviderLeg(provider_leg_id=mode.value, mode=mode, start=start, end=end, distance_m=100,
            duration_sec=100, geometry=[[126.97, 37.55], [126.98, 37.56]], route_name="100", line_name="1호선")
            for mode in [LegMode.WALK, LegMode.BUS, LegMode.SUBWAY]])


ROWS = {"getFcElvtr": {"row": [{"stnNm": "서울역", "dtlLoc": "1번 출구"}, {"stnNm": "시청역"}]}}


async def test_inventory_presence_does_not_prove_operation_and_cache_keeps_fetch_time():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=ROWS))) as http:
        source = SeoulDataClient("fixture", "fixture", http)
        facility = await source.get_elevator("서울역")
        assert facility.status == FacilityStatus.UNKNOWN
        assert facility.exists is True
        assert facility.confidence == DataConfidence.UNKNOWN
        assert facility.observed_at is None
        assert facility.fetched_at is not None
        again = await source.get_elevator("서울역")
        assert again.fetched_at == facility.fetched_at
        units = await source.get_station_elevators("서울역")
        assert units[0].status == FacilityStatus.UNKNOWN
        assert units[0].fetched_at == facility.fetched_at


async def test_empty_cache_shares_one_upstream_request_for_eight_callers():
    calls = 0
    async def fetch(_request):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)
        return httpx.Response(200, json=ROWS)
    async with httpx.AsyncClient(transport=httpx.MockTransport(fetch)) as http:
        source = SeoulDataClient("fixture", "fixture", http)
        result = await asyncio.gather(*(source.get_elevator("서울역") for _ in range(8)))
        assert calls == 1
        assert all(item.location_description == "1번 출구" for item in result)
        await asyncio.gather(*(source.get_elevator("서울역") for _ in range(8)))
        assert calls == 1


@pytest.mark.parametrize("application_error", [False, True])
async def test_failed_shared_request_is_not_cached_and_next_call_retries(application_error):
    calls = 0
    async def fetch(_request):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)
        if calls == 1:
            return httpx.Response(200, json={"RESULT": {"CODE": "ERROR-300"}}) if application_error else httpx.Response(503)
        return httpx.Response(200, json=ROWS)
    async with httpx.AsyncClient(transport=httpx.MockTransport(fetch)) as http:
        source = SeoulDataClient("fixture", "fixture", http)
        results = await asyncio.gather(*(source.get_elevator("서울역") for _ in range(8)), return_exceptions=True)
        assert all(isinstance(result, ApiError) for result in results)
        assert calls == 1
        assert (await source.get_elevator("서울역")).location_description == "1번 출구"
        assert calls == 2


async def test_one_cancelled_waiter_does_not_cancel_shared_request():
    started, finish = asyncio.Event(), asyncio.Event()
    calls = 0
    async def fetch(_request):
        nonlocal calls
        calls += 1
        started.set()
        await finish.wait()
        return httpx.Response(200, json=ROWS)
    async with httpx.AsyncClient(transport=httpx.MockTransport(fetch)) as http:
        source = SeoulDataClient("fixture", "fixture", http)
        first = asyncio.create_task(source.get_elevator("서울역"))
        second = asyncio.create_task(source.get_elevator("시청역"))
        await started.wait()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        finish.set()
        assert (await second).exists is True
        assert calls == 1


async def test_live_mode_never_substitutes_synthetic_accessibility_on_upstream_failure():
    container = build_container(Settings(
        route_provider="tmap", tmap_app_key="fixture", seoul_api_key="fixture",
        seoul_subway_api_key="fixture", _env_file=None))
    # Only transport is replaced: production container/provider wiring remains in use.
    await container.http_client.aclose()
    container.http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    provider = container.route_service.accessibility
    provider.seoul.client = container.http_client
    try:
        context = await provider.get_context([route()])
        assert context.walk['WALK'].source == DataSource.UNKNOWN
        assert context.walk['WALK'].confidence == DataConfidence.UNKNOWN
        assert context.bus['BUS'].source != DataSource.SYNTHETIC_FIXTURE
        assert context.subway['SUBWAY'].source != DataSource.SYNTHETIC_FIXTURE
        assert context.subway['SUBWAY'].elevator_status == FacilityStatus.UNKNOWN
        assert not context.bus['BUS'].departures
    finally:
        await container.close()


async def test_live_inventory_remains_unknown_in_route_context():
    container = build_container(Settings(
        route_provider="tmap", tmap_app_key="fixture", seoul_api_key="fixture",
        seoul_subway_api_key="fixture", _env_file=None))
    await container.http_client.aclose()
    container.http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=ROWS)))
    container.route_service.accessibility.seoul.client = container.http_client
    try:
        context = await container.route_service.accessibility.get_context([route()])
        value = context.subway['SUBWAY']
        assert value.elevator_status == FacilityStatus.UNKNOWN
        assert value.confidence == DataConfidence.UNKNOWN
        assert value.observed_at is None
        assert value.fetched_at is not None
    finally:
        await container.close()


async def test_cache_expiry_fetches_again(monkeypatch):
    import app.providers.seoul as module
    now = [0.0]
    monkeypatch.setattr(module, "monotonic", lambda: now[0])
    calls = 0
    def fetch(_):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=ROWS)
    async with httpx.AsyncClient(transport=httpx.MockTransport(fetch)) as http:
        source = SeoulDataClient("fixture", "fixture", http, elevator_cache_ttl_sec=10)
        await source.get_elevator("서울역")
        now[0] = 9.0
        await source.get_elevator("서울역")
        assert calls == 1
        now[0] = 10.0
        await source.get_elevator("서울역")
        assert calls == 2


async def test_facility_inventory_metadata_survives_api_serialization():
    from test_contract_responses import assert_schema

    from app.main import create_app
    settings = Settings(route_provider="tmap", tmap_app_key="fixture", seoul_api_key="fixture",
                        seoul_subway_api_key="fixture", _env_file=None)
    container = build_container(settings)
    await container.http_client.aclose()
    container.http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=ROWS)))
    container.route_service.accessibility.seoul.client = container.http_client
    candidate = route()
    class Routes:
        async def search(self, _request):
            return [candidate]
    container.route_service.provider = Routes()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(settings, container)), base_url="http://test") as http:
            response = await http.post("/api/v1/routes/search", headers={"Authorization": "Bearer demo-token"}, json={
                "origin": candidate.legs[0].start.model_dump(by_alias=True),
                "destination": candidate.legs[0].end.model_dump(by_alias=True), "mode": "TRANSIT"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["dataMode"] == "LIVE"
        assert_schema(payload, "RouteSearchResponse")
        facilities = [facility for result in payload["routes"] for leg in result["legs"]
                      if leg["mode"] == "SUBWAY" for facility in leg["facilities"]]
        assert facilities
        for facility in facilities:
            assert facility["exists"] is True
            assert facility["status"] == "UNKNOWN"
            assert facility["dataConfidence"] == "UNKNOWN"
            assert facility["dataSource"] == "SEOUL_OPEN_DATA"
            assert facility["fetchedAt"]
            assert "observedAt" not in facility
    finally:
        await container.close()


async def test_demo_mode_keeps_synthetic_data_explicit():
    container = build_container(Settings(route_provider="mock", _env_file=None))
    try:
        context = await container.route_service.accessibility.get_context([route()])
        assert context.walk["WALK"].source == DataSource.SYNTHETIC_FIXTURE
        assert context.bus["BUS"].source == DataSource.SYNTHETIC_FIXTURE
        assert context.subway["SUBWAY"].source == DataSource.SYNTHETIC_FIXTURE
        assert context.subway["SUBWAY"].confidence == DataConfidence.ESTIMATED
    finally:
        await container.close()


@pytest.mark.parametrize('payload', [
    {'getFcElvtr': {'RESULT': 'bad'}},
    {'response': {'header': 'bad'}},
    {'response': {'header': {'resultCode': '00'}, 'body': ['bad']}},
    {'RESULT': 'bad'},
])
async def test_malformed_inventory_is_an_upstream_error(payload):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as http:
        source = SeoulDataClient('fixture', 'fixture', http)
        with pytest.raises(ApiError):
            await source.get_elevator('서울역')
        assert source._elevator_rows is None
