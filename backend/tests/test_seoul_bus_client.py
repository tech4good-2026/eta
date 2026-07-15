import httpx
import pytest
import respx

from app.models import Coordinate, LowFloorStatus, PlaceInput
from app.providers.seoul_bus import SeoulBusClient

ROUTE_RESPONSE = {
    "comMsgHeader": None,
    "msgHeader": {
        "headerCd": "0",
        "headerMsg": "정상적으로 처리되었습니다.",
        "itemCount": 1,
    },
    "msgBody": {
        "itemList": [
            {
                "busRouteId": "100100301",
                "busRouteNm": "301",
                "routeType": "3",
                "stStationNm": "혜화동",
                "edStationNm": "장지공영차고지",
            }
        ]
    },
}

STATION_RESPONSE = {
    "comMsgHeader": None,
    "msgHeader": {
        "headerCd": "0",
        "headerMsg": "정상적으로 처리되었습니다.",
        "itemCount": 2,
    },
    "msgBody": {
        "itemList": [
            {
                "busRouteId": "100100301",
                "busRouteNm": "301",
                "seq": "1",
                "station": "101000001",
                "stationNm": "동대문역사문화공원역8번출구",
                "gpsX": "127.007283",
                "gpsY": "37.565033",
                "direction": "장충동",
                "stationNo": "02174",
                "routeType": "3",
            },
            {
                "busRouteId": "100100301",
                "busRouteNm": "301",
                "seq": "2",
                "station": "101000002",
                "stationNm": "반대편 정류장",
                "gpsX": "127.020000",
                "gpsY": "37.580000",
                "direction": "혜화동",
                "stationNo": "02175",
                "routeType": "3",
            },
        ]
    },
}

ARRIVAL_RESPONSE = {
    "comMsgHeader": None,
    "msgHeader": {
        "headerCd": "0",
        "headerMsg": "정상적으로 처리되었습니다.",
        "itemCount": 2,
    },
    "msgBody": {
        "itemList": [
            {
                "arrmsg1": "2분 후",
                "arrmsg2": "8분 후",
                "arsId": "02174",
                "busRouteAbrv": "301",
                "busRouteId": "100100301",
                "busType1": "0",
                "busType2": "1",
                "exps1": "120",
                "exps2": "480",
                "plainNo1": "서울74사1234",
                "plainNo2": "서울74사5678",
                "rtNm": "301",
                "stId": "101000001",
                "stNm": "동대문역사문화공원역8번출구",
                "vehId1": "111111111",
                "vehId2": "222222222",
            },
            {
                "arrmsg1": "5분 후",
                "arrmsg2": "12분 후",
                "arsId": "02175",
                "busRouteAbrv": "301",
                "busRouteId": "100100301",
                "busType1": "1",
                "busType2": "1",
                "exps1": "300",
                "exps2": "720",
                "plainNo1": "서울74사9999",
                "plainNo2": "서울74사8888",
                "rtNm": "301",
                "stId": "101000002",
                "stNm": "반대편 정류장",
                "vehId1": "333333333",
                "vehId2": "444444444",
            },
        ]
    },
}


@pytest.mark.asyncio
@respx.mock
async def test_bus_arrivals_resolve_tmap_route_and_stop_and_keep_vehicle_type() -> None:
    route_lookup = respx.get(
        "http://ws.bus.go.kr/api/rest/busRouteInfo/getBusRouteList"
    ).mock(return_value=httpx.Response(200, json=ROUTE_RESPONSE))
    station_lookup = respx.get(
        "http://ws.bus.go.kr/api/rest/busRouteInfo/getStaionByRoute"
    ).mock(return_value=httpx.Response(200, json=STATION_RESPONSE))
    arrival_lookup = respx.get(
        "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByRouteAll"
    ).mock(return_value=httpx.Response(200, json=ARRIVAL_RESPONSE))
    stop = PlaceInput(
        name="동대문역사문화공원역8번출구",
        coordinate=Coordinate(latitude=37.565033, longitude=127.007283),
    )

    async with httpx.AsyncClient() as client:
        arrivals = await SeoulBusClient("decoded-service-key", client).get_arrivals(
            "간선:301", stop
        )

    assert [(value.arrival_sec, value.low_floor_status) for value in arrivals] == [
        (120, LowFloorStatus.NOT_LOW_FLOOR),
        (480, LowFloorStatus.CONFIRMED),
    ]
    assert arrivals[1].vehicle_id == "222222222"
    assert route_lookup.calls.last.request.url.params["strSrch"] == "301"
    assert station_lookup.calls.last.request.url.params["busRouteId"] == "100100301"
    assert arrival_lookup.calls.last.request.url.params["busRouteId"] == "100100301"


@pytest.mark.asyncio
@respx.mock
async def test_static_bus_mapping_is_cached_but_arrivals_are_refreshed() -> None:
    route_lookup = respx.get(
        "http://ws.bus.go.kr/api/rest/busRouteInfo/getBusRouteList"
    ).mock(return_value=httpx.Response(200, json=ROUTE_RESPONSE))
    station_lookup = respx.get(
        "http://ws.bus.go.kr/api/rest/busRouteInfo/getStaionByRoute"
    ).mock(return_value=httpx.Response(200, json=STATION_RESPONSE))
    arrival_lookup = respx.get(
        "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByRouteAll"
    ).mock(return_value=httpx.Response(200, json=ARRIVAL_RESPONSE))
    stop = PlaceInput(
        name="동대문역사문화공원역8번출구",
        coordinate=Coordinate(latitude=37.565033, longitude=127.007283),
    )

    async with httpx.AsyncClient() as client:
        bus = SeoulBusClient("decoded-service-key", client)
        await bus.get_arrivals("간선:301", stop)
        await bus.get_arrivals("간선:301", stop)

    assert route_lookup.call_count == 1
    assert station_lookup.call_count == 1
    assert arrival_lookup.call_count == 2
