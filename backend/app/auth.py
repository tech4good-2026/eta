from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings
from app.errors import ApiError

bearer = HTTPBearer(auto_error=False)


def require_demo_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    settings: Settings = request.app.state.settings
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or credentials.credentials != settings.demo_token
    ):
        raise ApiError(401, "UNAUTHORIZED", "유효한 인증 토큰이 필요합니다.")
    return "usr_demo_001"


DemoUser = Annotated[str, Depends(require_demo_user)]
