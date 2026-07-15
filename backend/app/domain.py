from dataclasses import dataclass, field
from datetime import datetime

from app.models import (
    DataConfidence,
    DataSource,
    FacilityStatus,
    LegMode,
    LowFloorStatus,
    PlaceInput,
    RouteMode,
    TimeSource,
)


@dataclass(frozen=True)
class ProviderWalkStep:
    instruction: str
    distance_m: int
    geometry: list[list[float]]
    street_name: str | None = None


@dataclass(frozen=True)
class ProviderLeg:
    provider_leg_id: str
    mode: LegMode
    start: PlaceInput
    end: PlaceInput
    distance_m: int
    duration_sec: int
    geometry: list[list[float]]
    steps: list[ProviderWalkStep] = field(default_factory=list)
    route_id: str | None = None
    route_name: str | None = None
    line_id: str | None = None
    line_name: str | None = None
    line_color: str | None = None
    departure_at: datetime | None = None
    arrival_at: datetime | None = None
    time_source: TimeSource = TimeSource.ESTIMATED
    expected_fare_krw: int | None = None


@dataclass(frozen=True)
class ProviderRoute:
    provider_route_id: str
    mode: RouteMode
    title: str
    standard_duration_sec: int
    total_distance_m: int
    walk_distance_m: int
    transfer_count: int
    fare_krw: int
    legs: list[ProviderLeg]


@dataclass(frozen=True)
class WalkAccessibility:
    has_stairs: bool | None = None
    max_slope_percent: float | None = None
    confidence: DataConfidence = DataConfidence.UNKNOWN
    source: DataSource = DataSource.UNKNOWN


@dataclass(frozen=True)
class RealtimeDeparture:
    departure_at: datetime
    low_floor_status: LowFloorStatus = LowFloorStatus.UNKNOWN
    vehicle_id: str | None = None
    direction: str | None = None


@dataclass(frozen=True)
class BusAccessibility:
    low_floor_status: LowFloorStatus = LowFloorStatus.UNKNOWN
    confidence: DataConfidence = DataConfidence.UNKNOWN
    source: DataSource = DataSource.UNKNOWN
    departures: tuple[RealtimeDeparture, ...] = ()


@dataclass(frozen=True)
class StationAccessibility:
    elevator_status: FacilityStatus | None = None
    confidence: DataConfidence = DataConfidence.UNKNOWN
    location_description: str | None = None
    observed_at: datetime | None = None
    source: DataSource = DataSource.UNKNOWN
    departures: tuple[RealtimeDeparture, ...] = ()


@dataclass(frozen=True)
class AccessibilityContext:
    walk: dict[str, WalkAccessibility] = field(default_factory=dict)
    bus: dict[str, BusAccessibility] = field(default_factory=dict)
    subway: dict[str, StationAccessibility] = field(default_factory=dict)
