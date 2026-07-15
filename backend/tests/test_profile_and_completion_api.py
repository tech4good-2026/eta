from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

AUTH = {"Authorization": "Bearer demo-token"}


def make_client() -> TestClient:
    return TestClient(
        create_app(
            Settings(
                route_provider="mock",
                demo_token="demo-token",
                cors_origins=["http://localhost:5173"],
            )
        )
    )


def route_request(mode: str) -> dict:
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


def replace_profile(client: TestClient, mobility_aids: list[str]) -> dict:
    response = client.put(
        "/api/v1/users/me/profile",
        headers=AUTH,
        json={
            "travelerTypes": ["SENIOR"],
            "mobilityAids": mobility_aids,
            "preferences": {
                "avoidStairs": False,
                "elevatorRequired": False,
                "lowFloorBusRequired": False,
                "avoidSteepSlopes": False,
            },
        },
    )
    assert response.status_code == 200
    return response.json()


def test_profile_replace_persists_and_is_used_by_route_search() -> None:
    with make_client() as client:
        before = client.post(
            "/api/v1/routes/search",
            headers=AUTH,
            json=route_request("TAXI"),
        )
        updated = replace_profile(client, [])
        fetched = client.get("/api/v1/users/me/profile", headers=AUTH)
        after = client.post(
            "/api/v1/routes/search",
            headers=AUTH,
            json=route_request("TAXI"),
        )

    assert before.status_code == 200
    assert any(
        warning["code"] == "WHEELCHAIR_TAXI_NOT_GUARANTEED"
        for warning in before.json()["routes"][0]["warnings"]
    )
    assert updated["travelerTypes"] == ["SENIOR"]
    assert updated["mobilityAids"] == []
    assert fetched.json() == updated
    assert not any(
        warning["code"] == "WHEELCHAIR_TAXI_NOT_GUARANTEED"
        for warning in after.json()["routes"][0]["warnings"]
    )


def test_profile_replace_recalculates_default_speed_and_walk_eta() -> None:
    with make_client() as client:
        before = client.post(
            "/api/v1/routes/search",
            headers=AUTH,
            json=route_request("WALK"),
        ).json()["routes"][0]

        updated = replace_profile(client, mobility_aids=[])
        after = client.post(
            "/api/v1/routes/search",
            headers=AUTH,
            json=route_request("WALK"),
        ).json()["routes"][0]

    assert updated["walkingSpeed"]["walkingSpeedSource"] == "PROFILE_DEFAULT"
    assert updated["walkingSpeed"]["walkingSpeedMps"] == 0.85
    assert (
        after["summary"]["personalizedDurationSec"]
        < before["summary"]["personalizedDurationSec"]
    )


def test_navigation_complete_is_idempotency_guarded_and_keeps_speed_without_samples() -> None:
    with make_client() as client:
        searched = client.post(
            "/api/v1/routes/search",
            headers=AUTH,
            json=route_request("WALK"),
        )
        route_id = searched.json()["routes"][0]["routeId"]
        started = client.post(
            "/api/v1/navigation/sessions",
            headers=AUTH,
            json={"routeId": route_id},
        ).json()
        session_id = started["sessionId"]
        sample_at = datetime.fromisoformat(started["updatedAt"]) + timedelta(seconds=5)
        positioned = client.post(
            f"/api/v1/navigation/sessions/{session_id}/position",
            headers=AUTH,
            json={
                "coordinate": {"latitude": 37.555, "longitude": 126.971},
                "recordedAt": sample_at.isoformat(),
                "accuracyM": 8,
            },
        )
        profile_before = client.get("/api/v1/users/me/profile", headers=AUTH).json()
        completed_at = sample_at + timedelta(minutes=10)
        completed = client.post(
            f"/api/v1/navigation/sessions/{session_id}/complete",
            headers=AUTH,
            json={"reason": "ARRIVED", "completedAt": completed_at.isoformat()},
        )
        duplicate = client.post(
            f"/api/v1/navigation/sessions/{session_id}/complete",
            headers=AUTH,
            json={"reason": "ARRIVED", "completedAt": completed_at.isoformat()},
        )
        state = client.app.state.container.navigation_service.debug_state(session_id)

    assert positioned.status_code == 200
    assert completed.status_code == 200
    assert completed.json() == {
        "sessionId": session_id,
        "status": "COMPLETED",
        "routeRevision": 1,
        "completedAt": completed_at.isoformat(),
        "walkingSpeedUpdated": False,
        "walkingSpeed": profile_before["walkingSpeed"],
    }
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "SESSION_ALREADY_COMPLETED"
    assert state.session.status == "COMPLETED"
    assert not hasattr(state, "last_coordinate")
    assert not hasattr(state, "position_samples")
