import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import build_container, create_app
from app.providers.seoul_bus import SeoulBusClient


def make_client() -> TestClient:
    settings = Settings(
        route_provider="mock",
        demo_token="demo-token",
        cors_origins=["http://localhost:5173"],
    )
    return TestClient(create_app(settings))


def test_health_reports_mock_provider() -> None:
    with make_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "routeProvider": "mock"}


def test_profile_requires_bearer_token() -> None:
    with make_client() as client:
        response = client.get("/api/v1/users/me/profile")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert response.json()["error"]["requestId"].startswith("req_")


def test_profile_rejects_unknown_bearer_token() -> None:
    with make_client() as client:
        response = client.get(
            "/api/v1/users/me/profile",
            headers={"Authorization": "Bearer not-the-demo-token"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_profile_returns_fixed_demo_profile() -> None:
    with make_client() as client:
        response = client.get(
            "/api/v1/users/me/profile",
            headers={"Authorization": "Bearer demo-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["userId"] == "usr_demo_001"
    assert body["travelerTypes"] == ["MOBILITY_IMPAIRED"]
    assert body["mobilityAids"] == ["MANUAL_WHEELCHAIR"]
    assert body["walkingSpeed"]["walkingSpeedMps"] == 0.8


def test_tmap_mode_requires_both_tmap_and_seoul_keys() -> None:
    with pytest.raises(ValidationError, match="SEOUL_API_KEY"):
        Settings(
            route_provider="tmap",
            tmap_app_key="tmap-key",
            seoul_api_key="",
            seoul_subway_api_key="seoul-subway-key",
        )


def test_tmap_mode_requires_separate_subway_key() -> None:
    with pytest.raises(ValidationError, match="SEOUL_SUBWAY_API_KEY"):
        Settings(
            route_provider="tmap",
            tmap_app_key="tmap-key",
            seoul_api_key="seoul-general-key",
            seoul_subway_api_key="",
        )


@pytest.mark.asyncio
async def test_tmap_mode_wires_optional_realtime_bus_client() -> None:
    settings = Settings(
        route_provider="tmap",
        tmap_app_key="tmap-key",
        seoul_api_key="seoul-general-key",
        seoul_subway_api_key="seoul-subway-key",
        seoul_bus_api_key="decoded-data-go-kr-key",
    )

    container = build_container(settings)
    try:
        assert isinstance(container.route_service.accessibility.bus, SeoulBusClient)
    finally:
        await container.close()
