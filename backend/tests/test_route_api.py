from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage import MemoryTTLStore, StoreState

AUTH = {"Authorization": "Bearer demo-token"}


def route_request(mode: str = "WALK") -> dict:
    return {
        "origin": {
            "name": "서울역",
            "coordinate": {"latitude": 37.5547, "longitude": 126.9707},
        },
        "destination": {
            "name": "서울시청",
            "coordinate": {"latitude": 37.5663, "longitude": 126.9779},
        },
        "mode": mode,
        "departureAt": "2026-07-15T14:00:00+09:00",
    }


def make_client(**overrides) -> TestClient:
    values = {
        "route_provider": "mock",
        "demo_token": "demo-token",
        "cors_origins": ["http://localhost:5173"],
    }
    values.update(overrides)
    return TestClient(create_app(Settings(**values)))


def test_search_and_get_personalized_walk_route() -> None:
    with make_client() as client:
        searched = client.post("/api/v1/routes/search", headers=AUTH, json=route_request())

        assert searched.status_code == 200
        body = searched.json()
        assert body["status"] == "SUCCESS"
        assert body["mode"] == "WALK"
        assert len(body["routes"]) == 1
        assert (
            body["routes"][0]["summary"]["personalizedDurationSec"]
            > body["routes"][0]["summary"]["standardDurationSec"]
        )
        assert body["routes"][0]["legs"][0]["geometry"]["coordinates"][0] == [
            126.9707,
            37.5547,
        ]
        generated = datetime.fromisoformat(body["generatedAt"])
        expires = datetime.fromisoformat(body["expiresAt"])
        assert expires - generated == timedelta(minutes=10)

        route_id = body["routes"][0]["routeId"]
        fetched = client.get(f"/api/v1/routes/{route_id}", headers=AUTH)

    assert fetched.status_code == 200
    assert fetched.json()["routeId"] == route_id


def test_each_mock_route_mode_uses_the_same_public_contract() -> None:
    with make_client() as client:
        responses = {
            mode: client.post(
                "/api/v1/routes/search", headers=AUTH, json=route_request(mode)
            )
            for mode in ["TRANSIT", "TAXI", "WALK"]
        }

    assert all(response.status_code == 200 for response in responses.values())
    assert responses["TRANSIT"].json()["routes"][0]["legs"][1]["mode"] == "SUBWAY"
    assert responses["TAXI"].json()["routes"][0]["summary"]["fareKrw"] > 0
    assert responses["WALK"].json()["routes"][0]["summary"]["walkDistanceM"] > 0


def test_invalid_route_request_uses_standard_error_shape() -> None:
    invalid = route_request()
    invalid["unexpected"] = True
    with make_client() as client:
        response = client.post("/api/v1/routes/search", headers=AUTH, json=invalid)

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["errors"]


def test_missing_route_is_distinct_from_expired_route() -> None:
    with make_client() as client:
        response = client.get("/api/v1/routes/route_missing", headers=AUTH)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROUTE_NOT_FOUND"


def test_memory_store_keeps_expired_tombstone_without_returning_value() -> None:
    now = datetime(2026, 7, 15, 14, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    current = [now]
    store: MemoryTTLStore[str] = MemoryTTLStore(clock=lambda: current[0])
    store.put("route-1", "private route", ttl_sec=10)

    assert store.get("route-1").state == StoreState.ACTIVE
    current[0] += timedelta(seconds=11)
    result = store.get("route-1")

    assert result.state == StoreState.EXPIRED
    assert result.value is None
