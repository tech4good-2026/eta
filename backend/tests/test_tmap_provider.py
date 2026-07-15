from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from app.errors import ApiError
from app.models import Coordinate, PlaceInput, RouteMode, RouteSearchRequest
from app.providers.tmap import TmapRouteProvider

SEOUL = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 7, 15, 14, 0, tzinfo=SEOUL)


def search_request(mode: RouteMode) -> RouteSearchRequest:
    return RouteSearchRequest(
        origin=PlaceInput(
            name="서울역",
            coordinate=Coordinate(latitude=37.5547, longitude=126.9707),
        ),
        destination=PlaceInput(
            name="시청",
            coordinate=Coordinate(latitude=37.5663, longitude=126.9779),
        ),
        mode=mode,
        departure_at=NOW,
    )


@pytest.mark.asyncio
@respx.mock
async def test_transit_request_and_response_are_normalized() -> None:
    upstream = respx.post("https://apis.openapi.sk.com/transit/routes").mock(
        return_value=httpx.Response(
            200,
            json={
                "metaData": {
                    "plan": {
                        "itineraries": [
                            {
                                "totalTime": 600,
                                "totalDistance": 3000,
                                "totalWalkDistance": 200,
                                "transferCount": 0,
                                "fare": {"regular": {"totalFare": 1500}},
                                "legs": [
                                    {
                                        "mode": "WALK",
                                        "sectionTime": 200,
                                        "distance": 200,
                                        "start": {"name": "서울역", "lon": 126.9707, "lat": 37.5547},
                                        "end": {"name": "서울역 정류장", "lon": 126.972, "lat": 37.556},
                                        "passShape": {"linestring": "126.9707,37.5547 126.972,37.556"},
                                        "steps": [{"description": "정류장까지 이동", "distance": 200}],
                                    },
                                    {
                                        "mode": "BUS",
                                        "sectionTime": 400,
                                        "distance": 2800,
                                        "routeId": "100100001",
                                        "route": "100번",
                                        "start": {"name": "서울역 정류장", "lon": 126.972, "lat": 37.556},
                                        "end": {"name": "시청 정류장", "lon": 126.9779, "lat": 37.5663},
                                        "passShape": {"linestring": "126.972,37.556 126.9779,37.5663"},
                                    },
                                ],
                            }
                        ]
                    }
                }
            },
        )
    )
    async with httpx.AsyncClient() as client:
        provider = TmapRouteProvider("secret", client)
        [route] = await provider.search(search_request(RouteMode.TRANSIT))

    sent = upstream.calls[0].request
    assert sent.headers["appkey"] == "secret"
    assert b'"startX":"126.9707"' in sent.content
    assert route.mode == RouteMode.TRANSIT
    assert route.fare_krw == 1500
    assert [leg.mode for leg in route.legs] == ["WALK", "BUS"]
    assert route.legs[1].route_name == "100번"
    assert route.legs[1].geometry[-1] == [126.9779, 37.5663]


@pytest.mark.asyncio
@respx.mock
async def test_pedestrian_geojson_is_normalized() -> None:
    respx.post("https://apis.openapi.sk.com/tmap/routes/pedestrian").mock(
        return_value=httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [126.9707, 37.5547]},
                        "properties": {"totalDistance": 800, "totalTime": 900},
                    },
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[126.9707, 37.5547], [126.9779, 37.5663]],
                        },
                        "properties": {"description": "세종대로를 따라 이동", "distance": 800},
                    },
                ],
            },
        )
    )
    async with httpx.AsyncClient() as client:
        [route] = await TmapRouteProvider("secret", client).search(search_request(RouteMode.WALK))

    assert route.mode == RouteMode.WALK
    assert route.total_distance_m == 800
    assert route.legs[0].duration_sec == 900
    assert route.legs[0].steps[0].instruction == "세종대로를 따라 이동"


@pytest.mark.asyncio
@respx.mock
async def test_car_geojson_becomes_taxi_route_with_estimated_fare() -> None:
    respx.post("https://apis.openapi.sk.com/tmap/routes").mock(
        return_value=httpx.Response(
            200,
            json={
                "features": [
                    {
                        "geometry": {"type": "Point", "coordinates": [126.9707, 37.5547]},
                        "properties": {"totalDistance": 2500, "totalTime": 540, "taxiFare": 7200},
                    },
                    {
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[126.9707, 37.5547], [126.9779, 37.5663]],
                        },
                        "properties": {},
                    },
                ]
            },
        )
    )
    async with httpx.AsyncClient() as client:
        [route] = await TmapRouteProvider("secret", client).search(search_request(RouteMode.TAXI))

    assert route.mode == RouteMode.TAXI
    assert route.fare_krw == 7200
    assert route.legs[0].expected_fare_krw == 7200


@pytest.mark.asyncio
@respx.mock
async def test_tmap_timeout_is_exposed_without_mock_fallback() -> None:
    respx.post("https://apis.openapi.sk.com/transit/routes").mock(
        side_effect=httpx.ReadTimeout("slow upstream")
    )
    async with httpx.AsyncClient() as client:
        provider = TmapRouteProvider("secret", client)
        with pytest.raises(ApiError) as caught:
            await provider.search(search_request(RouteMode.TRANSIT))

    assert caught.value.status_code == 503
    assert caught.value.code == "UPSTREAM_UNAVAILABLE"
    assert caught.value.details == {"provider": "TMAP", "retryable": True}


@pytest.mark.asyncio
@respx.mock
async def test_tmap_rate_limit_and_invalid_payload_have_distinct_errors() -> None:
    route = respx.post("https://apis.openapi.sk.com/transit/routes")
    route.side_effect = [httpx.Response(429), httpx.Response(200, json={"unexpected": True})]
    async with httpx.AsyncClient() as client:
        provider = TmapRouteProvider("secret", client)
        with pytest.raises(ApiError) as limited:
            await provider.search(search_request(RouteMode.TRANSIT))
        with pytest.raises(ApiError) as invalid:
            await provider.search(search_request(RouteMode.TRANSIT))

    assert limited.value.status_code == 429
    assert limited.value.code == "RATE_LIMITED"
    assert invalid.value.status_code == 502
    assert invalid.value.code == "UPSTREAM_INVALID_RESPONSE"
