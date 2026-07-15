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


def search_route(client: TestClient, mode: str = "TRANSIT") -> dict:
    response = client.post(
        "/api/v1/routes/search",
        headers=AUTH,
        json={
            "origin": {
                "name": "서울역",
                "coordinate": {"latitude": 37.5547, "longitude": 126.9707},
            },
            "destination": {
                "name": "잠실역",
                "coordinate": {"latitude": 37.5133, "longitude": 127.1001},
            },
            "mode": mode,
            "departureAt": "2026-07-15T14:00:00+09:00",
        },
    )
    assert response.status_code == 200
    return response.json()["routes"][0]


def start_navigation(client: TestClient, route_id: str) -> dict:
    response = client.post(
        "/api/v1/navigation/sessions",
        headers=AUTH,
        json={"routeId": route_id},
    )
    assert response.status_code == 201
    return response.json()


def position_payload(latitude: float, longitude: float, recorded_at: datetime) -> dict:
    return {
        "coordinate": {"latitude": latitude, "longitude": longitude},
        "recordedAt": recorded_at.isoformat(),
        "accuracyM": 10,
    }


def test_start_position_off_route_and_confirmed_reroute_keep_session() -> None:
    with make_client() as client:
        initial_route = search_route(client)
        started = start_navigation(client, initial_route["routeId"])
        session_id = started["sessionId"]
        first_sample_at = datetime.fromisoformat(started["updatedAt"]) + timedelta(seconds=5)

        first = client.post(
            f"/api/v1/navigation/sessions/{session_id}/position",
            headers=AUTH,
            json=position_payload(37.70, 127.30, first_sample_at),
        )
        second = client.post(
            f"/api/v1/navigation/sessions/{session_id}/position",
            headers=AUTH,
            json=position_payload(37.70, 127.30, first_sample_at + timedelta(seconds=5)),
        )

        assert first.status_code == 200
        assert first.json()["status"] == "ACTIVE"
        assert second.status_code == 200
        assert second.json()["status"] == "REROUTE_SUGGESTED"
        assert second.json()["rerouteSuggestion"]["reason"] == "OFF_ROUTE"

        rerouted = client.post(
            f"/api/v1/navigation/sessions/{session_id}/reroute",
            headers=AUTH,
            json={
                "reason": "OFF_ROUTE",
                "currentLocation": position_payload(
                    37.70, 127.30, first_sample_at + timedelta(seconds=10)
                ),
            },
        )

    assert rerouted.status_code == 200
    body = rerouted.json()
    assert body["sessionId"] == session_id
    assert body["routeRevision"] == 2
    assert body["status"] == "ACTIVE"
    assert body["route"]["routeId"] != initial_route["routeId"]
    assert body["route"]["summary"]["departureAt"] != initial_route["summary"]["departureAt"]


def test_missed_subway_is_suggested_after_two_samples_near_boarding_station() -> None:
    with make_client() as client:
        route = search_route(client)
        started = start_navigation(client, route["routeId"])
        session_id = started["sessionId"]
        subway = next(leg for leg in route["legs"] if leg["mode"] == "SUBWAY")
        boarding = subway["boardingStation"]["coordinate"]
        departure = datetime.fromisoformat(subway["departureAt"])

        first = client.post(
            f"/api/v1/navigation/sessions/{session_id}/position",
            headers=AUTH,
            json=position_payload(
                boarding["latitude"], boarding["longitude"], departure + timedelta(seconds=70)
            ),
        )
        second = client.post(
            f"/api/v1/navigation/sessions/{session_id}/position",
            headers=AUTH,
            json=position_payload(
                boarding["latitude"], boarding["longitude"], departure + timedelta(seconds=75)
            ),
        )

    assert first.status_code == 200
    assert first.json()["status"] == "ACTIVE"
    assert second.status_code == 200
    assert second.json()["status"] == "REROUTE_SUGGESTED"
    assert second.json()["rerouteSuggestion"]["reason"] == "MISSED_TRANSIT"
    assert second.json()["routeRevision"] == 1


def test_position_faster_than_five_seconds_is_ignored_without_storing_raw_coordinate() -> None:
    with make_client() as client:
        route = search_route(client, "WALK")
        started = start_navigation(client, route["routeId"])
        session_id = started["sessionId"]
        start_time = datetime.fromisoformat(started["updatedAt"])
        first = client.post(
            f"/api/v1/navigation/sessions/{session_id}/position",
            headers=AUTH,
            json=position_payload(37.70, 127.30, start_time + timedelta(seconds=5)),
        )
        too_fast = client.post(
            f"/api/v1/navigation/sessions/{session_id}/position",
            headers=AUTH,
            json=position_payload(37.80, 127.40, start_time + timedelta(seconds=7)),
        )

        state = client.app.state.container.navigation_service.debug_state(session_id)

    assert first.json()["status"] == "ACTIVE"
    assert too_fast.json()["status"] == "ACTIVE"
    assert state.off_route_sample_count == 1
    assert not hasattr(state, "last_coordinate")
    assert not hasattr(state, "position_samples")


def test_current_station_takes_precedence_over_gps_when_rerouting() -> None:
    with make_client() as client:
        route = search_route(client)
        started = start_navigation(client, route["routeId"])
        recorded_at = datetime.fromisoformat(started["updatedAt"]) + timedelta(minutes=1)
        rerouted = client.post(
            f"/api/v1/navigation/sessions/{started['sessionId']}/reroute",
            headers=AUTH,
            json={
                "reason": "MISSED_TRANSIT",
                "currentLocation": position_payload(35.0, 128.0, recorded_at),
                "currentStation": {
                    "providerPlaceId": "station_cityhall_201",
                    "name": "시청역",
                    "coordinate": {"latitude": 37.5640, "longitude": 126.9768},
                },
            },
        )

    assert rerouted.status_code == 200
    route_start = rerouted.json()["route"]["legs"][0]["start"]
    assert route_start["name"] == "시청역"
    assert route_start["coordinate"] == {"latitude": 37.564, "longitude": 126.9768}


def test_unknown_navigation_session_returns_standard_error() -> None:
    with make_client() as client:
        response = client.post(
            "/api/v1/navigation/sessions/nav_missing/position",
            headers=AUTH,
            json=position_payload(
                37.5, 127.0, datetime.fromisoformat("2026-07-15T14:00:00+09:00")
            ),
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"
