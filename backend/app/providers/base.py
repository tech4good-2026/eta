from typing import Protocol

from app.domain import AccessibilityContext, ProviderRoute
from app.models import RouteSearchRequest


class RouteProvider(Protocol):
    async def search(self, request: RouteSearchRequest) -> list[ProviderRoute]: ...


class AccessibilityContextProvider(Protocol):
    async def get_context(self, routes: list[ProviderRoute]) -> AccessibilityContext: ...
