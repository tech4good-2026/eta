import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from app.domain import ProviderRoute
from app.errors import ApiError
from app.models import (
    AccessibilityStatus,
    Notice,
    Route,
    RouteMode,
    RouteSearchRequest,
    RouteSearchResponse,
    SearchStatus,
    UserProfile,
)
from app.personalization import PersonalizationEngine
from app.providers.base import AccessibilityContextProvider, RouteProvider
from app.storage import MemoryTTLStore, StoreState


@dataclass(frozen=True)
class StoredRoute:
    route: Route
    request: RouteSearchRequest


class RouteService:
    def __init__(
        self,
        provider: RouteProvider,
        accessibility: AccessibilityContextProvider,
        engine: PersonalizationEngine,
        store: MemoryTTLStore[StoredRoute],
        provider_cache: MemoryTTLStore[list[ProviderRoute]] | None = None,
        ttl_sec: int = 600,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.provider = provider
        self.accessibility = accessibility
        self.engine = engine
        self.store = store
        self.ttl_sec = ttl_sec
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.provider_cache = provider_cache or MemoryTTLStore[list[ProviderRoute]](
            clock=self.clock
        )

    async def search(
        self, request: RouteSearchRequest, profile: UserProfile
    ) -> RouteSearchResponse:
        cache_key = self._provider_cache_key(request)
        cached = self.provider_cache.get(cache_key)
        if cached.state == StoreState.ACTIVE and cached.value is not None:
            candidates = cached.value
        else:
            candidates = await self.provider.search(request)
            self.provider_cache.put(cache_key, candidates, self.ttl_sec)
        generated_at = self.clock()
        requested_at = request.departure_at or generated_at
        context = await self.accessibility.get_context(candidates)
        personalized = self.engine.personalize_routes(
            candidates, profile, context, requested_at
        )
        usable = [
            route
            for route in personalized
            if route.accessibility_status != AccessibilityStatus.UNAVAILABLE
        ]
        routes: list[Route] = []
        for rank, route in enumerate(usable, start=1):
            stored_route = route.model_copy(
                update={"route_id": f"route_{uuid4().hex}", "rank": rank}
            )
            self.store.put(
                stored_route.route_id,
                StoredRoute(route=stored_route, request=request),
                ttl_sec=self.ttl_sec,
            )
            routes.append(stored_route)

        if routes:
            status = SearchStatus.SUCCESS
            fallbacks: list[RouteMode] = []
            notices: list[Notice] = []
        else:
            status = SearchStatus.NO_ACCESSIBLE_ROUTE
            fallbacks = [RouteMode.TAXI] if request.mode == RouteMode.TRANSIT else []
            low_floor_failed = any(
                reason.code == "LOW_FLOOR_BUS_REQUIRED"
                for route in personalized
                for reason in route.unavailable_reasons
            )
            notices = [
                Notice(
                    code=(
                        "LOW_FLOOR_BUS_UNAVAILABLE"
                        if low_floor_failed
                        else "NO_ACCESSIBLE_ROUTE"
                    ),
                    severity="WARNING",
                    message=(
                        "필수 조건을 충족하는 저상버스 경로를 찾지 못했습니다."
                        if low_floor_failed
                        else "현재 조건을 충족하는 경로를 찾지 못했습니다."
                    ),
                )
            ]
        response = RouteSearchResponse(
            search_id=f"search_{uuid4().hex}",
            mode=request.mode,
            status=status,
            generated_at=generated_at,
            expires_at=generated_at + timedelta(seconds=self.ttl_sec),
            routes=routes,
            fallback_modes=fallbacks,
            notices=notices,
        )
        return response

    def get_stored_route(self, route_id: str) -> StoredRoute:
        result = self.store.get(route_id)
        if result.state == StoreState.EXPIRED:
            raise ApiError(410, "ROUTE_EXPIRED", "경로 유효시간이 만료되었습니다.")
        if result.state == StoreState.MISSING or result.value is None:
            raise ApiError(404, "ROUTE_NOT_FOUND", "경로를 찾을 수 없습니다.")
        return result.value

    def get_route(self, route_id: str) -> Route:
        return self.get_stored_route(route_id).route

    @staticmethod
    def _provider_cache_key(request: RouteSearchRequest) -> str:
        value = request.model_dump(mode="json", by_alias=True, exclude_none=True)
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
