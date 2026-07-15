import httpx
import pytest
import respx

from app.models import FacilityStatus
from app.providers.seoul import SeoulDataClient


@pytest.mark.asyncio
@respx.mock
async def test_elevator_presence_is_normalized_as_available() -> None:
    upstream = respx.get(url__regex=r"http://openapi\.seoul\.go\.kr:8088/.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "getFcElvtr": {
                    "row": [
                        {
                            "stnNm": "서울역",
                            "lineNm": "1호선",
                            "dtlLoc": "1번 출구 방면",
                        },
                        {
                            "stnNm": "시청역",
                            "lineNm": "1호선",
                            "dtlLoc": "환승 통로 방면",
                        },
                    ]
                }
            },
        )
    )
    async with httpx.AsyncClient() as client:
        seoul = SeoulDataClient("seoul-general-key", "seoul-subway-key", client)
        facility = await seoul.get_elevator("서울역")
        second = await seoul.get_elevator("시청역")

    assert facility is not None
    assert facility.status == FacilityStatus.AVAILABLE
    assert facility.location_description == "1번 출구 방면"
    assert second is not None
    assert upstream.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_elevator_supports_current_seoul_response_envelope() -> None:
    respx.get(url__regex=r"http://openapi\.seoul\.go\.kr:8088/.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
                    "body": {
                        "items": {
                            "item": [
                                {
                                    "stnNm": "서울역",
                                    "dtlPstn": "1번 출구 방면",
                                    "oprtngSitu": "운영중",
                                }
                            ]
                        },
                        "totalCount": 1,
                    },
                }
            },
        )
    )
    async with httpx.AsyncClient() as client:
        facility = await SeoulDataClient(
            "seoul-general-key",
            "seoul-subway-key",
            client,
        ).get_elevator("서울역")

    assert facility is not None
    assert facility.status == FacilityStatus.AVAILABLE
    assert facility.location_description == "1번 출구 방면"


@pytest.mark.asyncio
@respx.mock
async def test_station_elevator_units_include_location_and_floors() -> None:
    respx.get(url__regex=r"http://openapi\.seoul\.go\.kr:8088/.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00"},
                    "body": {
                        "items": {
                            "item": [
                                {
                                    "stnNm": "동묘앞",
                                    "lineNm": "1호선",
                                    "dtlPstn": "신설동 방면6-2",
                                    "bgngFlr": "B1",
                                    "endFlr": "4",
                                },
                                {
                                    "stnNm": "동묘앞",
                                    "lineNm": "1호선",
                                    "dtlPstn": "신설동 방면10-3",
                                    "bgngFlr": "B2",
                                    "endFlr": "B1",
                                },
                                {
                                    "stnNm": "시청",
                                    "lineNm": "1호선",
                                    "dtlPstn": "환승 통로",
                                    "bgngFlr": "B2",
                                    "endFlr": "B1",
                                },
                            ]
                        },
                        "totalCount": 3,
                    },
                }
            },
        )
    )
    async with httpx.AsyncClient() as client:
        units = await SeoulDataClient(
            "seoul-general-key",
            "seoul-subway-key",
            client,
        ).get_station_elevators("동묘앞역")

    assert len(units) == 2
    assert units[0].location_description == "신설동 방면6-2"
    assert units[0].floors == "B1~4"
    assert units[1].floors == "B2~B1"
    assert all(unit.status == FacilityStatus.AVAILABLE for unit in units)


@pytest.mark.asyncio
@respx.mock
async def test_realtime_subway_returns_soonest_nonnegative_arrival() -> None:
    upstream = respx.get(url__regex=r"http://swopenapi\.seoul\.go\.kr/.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "realtimeArrivalList": [
                    {"statnNm": "시청", "barvlDt": "180"},
                    {"statnNm": "시청", "barvlDt": "45"},
                ]
            },
        )
    )
    async with httpx.AsyncClient() as client:
        seconds = await SeoulDataClient(
            "seoul-general-key",
            "seoul-subway-key",
            client,
        ).get_next_arrival_sec("시청")

    assert seconds == 45
    assert "/seoul-subway-key/json/" in str(upstream.calls.last.request.url)


@pytest.mark.asyncio
@respx.mock
async def test_realtime_subway_arrivals_are_filtered_to_tmap_line() -> None:
    respx.get(url__regex=r"http://swopenapi\.seoul\.go\.kr/.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "errorMessage": {
                    "status": 200,
                    "code": "INFO-000",
                    "message": "정상 처리되었습니다.",
                    "total": 3,
                },
                "realtimeArrivalList": [
                    {
                        "subwayId": "1001",
                        "subwayNm": "1호선",
                        "statnNm": "서울",
                        "trainLineNm": "동묘앞행 - 상행",
                        "barvlDt": "20",
                        "btrainNo": "K101",
                        "bstatnNm": "동묘앞",
                    },
                    {
                        "subwayId": "1004",
                        "subwayNm": "4호선",
                        "statnNm": "서울",
                        "trainLineNm": "진접행 - 상행",
                        "barvlDt": "45",
                        "btrainNo": "K401",
                        "bstatnNm": "진접",
                    },
                    {
                        "subwayId": "1004",
                        "subwayNm": "4호선",
                        "statnNm": "서울",
                        "trainLineNm": "오이도행 - 하행",
                        "barvlDt": "180",
                        "btrainNo": "K402",
                        "bstatnNm": "오이도",
                    },
                ],
            },
        )
    )
    async with httpx.AsyncClient() as client:
        arrivals = await SeoulDataClient(
            "seoul-general-key",
            "seoul-subway-key",
            client,
        ).get_subway_arrivals("서울역", "수도권4호선")

    assert [arrival.arrival_sec for arrival in arrivals] == [45, 180]
    assert arrivals[0].train_id == "K401"
    assert arrivals[0].terminal_station == "진접"
