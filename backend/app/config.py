from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Tech4Good Accessible Navigation API"
    route_provider: Literal["mock", "tmap"] = "mock"
    demo_token: str = "demo-token"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    tmap_app_key: str | None = None
    seoul_api_key: str | None = None
    seoul_subway_api_key: str | None = None
    seoul_bus_api_key: str | None = None
    route_ttl_sec: int = 600
    navigation_ttl_sec: int = 7200
    upstream_timeout_sec: float = 5.0

    @model_validator(mode="after")
    def require_tmap_key_in_tmap_mode(self) -> "Settings":
        if self.route_provider == "tmap" and not self.tmap_app_key:
            raise ValueError("TMAP_APP_KEY is required when ROUTE_PROVIDER=tmap")
        if self.route_provider == "tmap" and not self.seoul_api_key:
            raise ValueError("SEOUL_API_KEY is required when ROUTE_PROVIDER=tmap")
        if self.route_provider == "tmap" and not self.seoul_subway_api_key:
            raise ValueError(
                "SEOUL_SUBWAY_API_KEY is required when ROUTE_PROVIDER=tmap"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
