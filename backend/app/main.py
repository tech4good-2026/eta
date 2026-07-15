from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.auth import DemoUser
from app.config import Settings, get_settings
from app.errors import ApiError, api_error_handler, validation_error_handler
from app.models import (
    CompleteNavigationRequest,
    LocationSample,
    MobilityAid,
    NavigationCompletion,
    NavigationSession,
    NavigationUpdate,
    ProfilePreferences,
    RerouteRequest,
    Route,
    RouteSearchRequest,
    RouteSearchResponse,
    StartNavigationRequest,
    TravelerType,
    UpdateProfileRequest,
    UserProfile,
    WalkingSpeedProfile,
)
from app.navigation import NavigationService, NavigationState
from app.personalization import BaselinePersonalizationEngine
from app.profile import DemoProfileStore
from app.providers.accessibility import HybridAccessibilityProvider
from app.providers.mock import MockRouteProvider
from app.providers.seoul import SeoulDataClient
from app.providers.seoul_bus import SeoulBusClient
from app.providers.tmap import TmapRouteProvider
from app.providers.walkway import MockWalkwaySource
from app.services import RouteService, StoredRoute
from app.storage import MemoryTTLStore

SEOUL = ZoneInfo("Asia/Seoul")


def demo_profile() -> UserProfile:
    return UserProfile(
        user_id="usr_demo_001",
        traveler_types=[TravelerType.MOBILITY_IMPAIRED],
        mobility_aids=[MobilityAid.MANUAL_WHEELCHAIR],
        preferences=ProfilePreferences(
            avoid_stairs=True,
            elevator_required=True,
            low_floor_bus_required=True,
            avoid_steep_slopes=True,
        ),
        walking_speed=WalkingSpeedProfile(
            walking_speed_mps=0.8,
            walking_speed_source="LEARNED",
            walking_speed_sample_count=12,
            updated_at=datetime(2026, 7, 15, 12, 40, tzinfo=SEOUL),
        ),
    )


@dataclass
class ApplicationContainer:
    route_service: RouteService
    navigation_service: NavigationService
    profile_store: DemoProfileStore
    http_client: httpx.AsyncClient | None = None

    async def close(self) -> None:
        if self.http_client is not None:
            await self.http_client.aclose()


def build_container(settings: Settings) -> ApplicationContainer:
    client: httpx.AsyncClient | None = None
    if settings.route_provider == "tmap":
        client = httpx.AsyncClient(timeout=settings.upstream_timeout_sec)
        route_provider = TmapRouteProvider(settings.tmap_app_key or "", client)
        seoul = (
            SeoulDataClient(
                settings.seoul_api_key,
                settings.seoul_subway_api_key,
                client,
            )
            if settings.seoul_api_key and settings.seoul_subway_api_key
            else None
        )
        bus = (
            SeoulBusClient(settings.seoul_bus_api_key, client)
            if settings.seoul_bus_api_key
            else None
        )
    else:
        route_provider = MockRouteProvider()
        seoul = None
        bus = None
    service = RouteService(
        provider=route_provider,
        accessibility=HybridAccessibilityProvider(
            seoul=seoul,
            bus=bus,
            use_synthetic_bus=settings.route_provider == "mock",
            # 데모용 목업: 경사 세그먼트와 저상버스 도착정보를 SYNTHETIC_FIXTURE로
            # 제공한다. 실데이터 어댑터가 준비되면 제거한다.
            walkway=MockWalkwaySource(),
            synthetic_bus_fallback=True,
        ),
        engine=BaselinePersonalizationEngine(),
        store=MemoryTTLStore[StoredRoute](),
        ttl_sec=settings.route_ttl_sec,
    )
    profile_store = DemoProfileStore(demo_profile())
    navigation_service = NavigationService(
        route_service=service,
        store=MemoryTTLStore[NavigationState](),
        ttl_sec=settings.navigation_ttl_sec,
        seoul=seoul,
        profile_store=profile_store,
    )
    return ApplicationContainer(
        route_service=service,
        navigation_service=navigation_service,
        profile_store=profile_store,
        http_client=client,
    )


def create_app(
    settings: Settings | None = None,
    container: ApplicationContainer | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    dependencies = container or build_container(resolved)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        await dependencies.close()

    app = FastAPI(title=resolved.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved
    app.state.container = dependencies
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "routeProvider": resolved.route_provider}

    @app.get(
        "/api/v1/users/me/profile",
        response_model=UserProfile,
        response_model_exclude_none=True,
    )
    async def get_profile(_user: DemoUser) -> UserProfile:
        return dependencies.profile_store.get()

    @app.put(
        "/api/v1/users/me/profile",
        response_model=UserProfile,
        response_model_exclude_none=True,
    )
    async def replace_profile(
        request: UpdateProfileRequest, _user: DemoUser
    ) -> UserProfile:
        return dependencies.profile_store.replace(request)

    @app.post(
        "/api/v1/routes/search",
        response_model=RouteSearchResponse,
        response_model_exclude_none=True,
    )
    async def search_routes(
        request: RouteSearchRequest, _user: DemoUser
    ) -> RouteSearchResponse:
        return await dependencies.route_service.search(
            request, dependencies.profile_store.get()
        )

    @app.get(
        "/api/v1/routes/{route_id}",
        response_model=Route,
        response_model_exclude_none=True,
    )
    async def get_route(route_id: str, _user: DemoUser) -> Route:
        return dependencies.route_service.get_route(route_id)

    @app.post(
        "/api/v1/navigation/sessions",
        response_model=NavigationSession,
        response_model_exclude_none=True,
        status_code=201,
    )
    async def start_navigation(
        request: StartNavigationRequest, _user: DemoUser
    ) -> NavigationSession:
        return dependencies.navigation_service.start(request.route_id)

    @app.post(
        "/api/v1/navigation/sessions/{session_id}/position",
        response_model=NavigationUpdate,
        response_model_exclude_none=True,
    )
    async def update_navigation_position(
        session_id: str, sample: LocationSample, _user: DemoUser
    ) -> NavigationUpdate:
        return await dependencies.navigation_service.update_position(session_id, sample)

    @app.post(
        "/api/v1/navigation/sessions/{session_id}/reroute",
        response_model=NavigationSession,
        response_model_exclude_none=True,
    )
    async def reroute_navigation(
        session_id: str, request: RerouteRequest, _user: DemoUser
    ) -> NavigationSession:
        return await dependencies.navigation_service.reroute(
            session_id, request, dependencies.profile_store.get()
        )

    @app.post(
        "/api/v1/navigation/sessions/{session_id}/complete",
        response_model=NavigationCompletion,
        response_model_exclude_none=True,
    )
    async def complete_navigation(
        session_id: str,
        request: CompleteNavigationRequest,
        _user: DemoUser,
    ) -> NavigationCompletion:
        return dependencies.navigation_service.complete(
            session_id, request, dependencies.profile_store.get()
        )

    return app


app = create_app()
