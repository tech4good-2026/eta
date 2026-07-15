from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from app.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
AUTH = {"Authorization": "Bearer demo-token"}


def assert_schema(instance: dict, schema_name: str) -> None:
    spec = yaml.safe_load((ROOT / "docs/openapi.yaml").read_text(encoding="utf-8"))
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/components/schemas/{schema_name}",
        "components": spec["components"],
    }
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    assert not errors, "\n".join(error.message for error in errors)


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


def test_runtime_responses_match_shared_openapi_contract() -> None:
    with make_client() as client:
        profile = client.get("/api/v1/users/me/profile", headers=AUTH)
        search = client.post(
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
                "mode": "TRANSIT",
                "departureAt": "2026-07-15T14:00:00+09:00",
            },
        )
        route = search.json()["routes"][0]
        fetched = client.get(f"/api/v1/routes/{route['routeId']}", headers=AUTH)
        started = client.post(
            "/api/v1/navigation/sessions",
            headers=AUTH,
            json={"routeId": route["routeId"]},
        )
        update = client.post(
            f"/api/v1/navigation/sessions/{started.json()['sessionId']}/position",
            headers=AUTH,
            json={
                "coordinate": {"latitude": 37.5547, "longitude": 126.9707},
                "recordedAt": "2026-07-15T14:00:05+09:00",
                "accuracyM": 10,
            },
        )
        error = client.get("/api/v1/users/me/profile")

    assert_schema(profile.json(), "UserProfile")
    assert_schema(search.json(), "RouteSearchResponse")
    assert_schema(fetched.json(), "Route")
    assert_schema(started.json(), "NavigationSession")
    assert_schema(update.json(), "NavigationUpdate")
    assert_schema(error.json(), "ErrorResponse")
