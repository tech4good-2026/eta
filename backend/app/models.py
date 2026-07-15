from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        use_enum_values=True,
    )


class TravelerType(StrEnum):
    PREGNANT = "PREGNANT"
    SENIOR = "SENIOR"
    MOBILITY_IMPAIRED = "MOBILITY_IMPAIRED"
    TEMPORARILY_INJURED = "TEMPORARILY_INJURED"
    CAREGIVER_WITH_CHILD = "CAREGIVER_WITH_CHILD"
    OTHER = "OTHER"


class MobilityAid(StrEnum):
    MANUAL_WHEELCHAIR = "MANUAL_WHEELCHAIR"
    POWER_WHEELCHAIR = "POWER_WHEELCHAIR"
    STROLLER = "STROLLER"
    CANE = "CANE"
    CRUTCHES = "CRUTCHES"
    WALKER = "WALKER"


class ProfilePreferences(ApiModel):
    avoid_stairs: bool
    elevator_required: bool
    low_floor_bus_required: bool
    avoid_steep_slopes: bool


class WalkingSpeedProfile(ApiModel):
    walking_speed_mps: float = Field(gt=0, le=3)
    walking_speed_source: str
    walking_speed_sample_count: int = Field(ge=0)
    updated_at: datetime


class UserProfile(ApiModel):
    user_id: str
    traveler_types: list[TravelerType] = Field(min_length=1)
    mobility_aids: list[MobilityAid]
    preferences: ProfilePreferences
    walking_speed: WalkingSpeedProfile


class RouteMode(StrEnum):
    TRANSIT = "TRANSIT"
    TAXI = "TAXI"
    WALK = "WALK"


class LegMode(StrEnum):
    WALK = "WALK"
    BUS = "BUS"
    SUBWAY = "SUBWAY"
    TAXI = "TAXI"


class AccessibilityStatus(StrEnum):
    ACCESSIBLE = "ACCESSIBLE"
    CAUTION = "CAUTION"
    UNAVAILABLE = "UNAVAILABLE"


class DataConfidence(StrEnum):
    VERIFIED = "VERIFIED"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"


class TimeSource(StrEnum):
    REALTIME = "REALTIME"
    SCHEDULED = "SCHEDULED"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"


class LowFloorStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    EXPECTED = "EXPECTED"
    NOT_LOW_FLOOR = "NOT_LOW_FLOOR"
    UNKNOWN = "UNKNOWN"


class FacilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class DataSource(StrEnum):
    TMAP = "TMAP"
    SEOUL_OPEN_DATA = "SEOUL_OPEN_DATA"
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    TEAM_ENGINE = "TEAM_ENGINE"
    UNKNOWN = "UNKNOWN"


class Coordinate(ApiModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class PlaceInput(ApiModel):
    provider_place_id: str | None = None
    name: str = Field(min_length=1)
    address: str | None = None
    coordinate: Coordinate


class GeoJsonLineString(ApiModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]] = Field(min_length=2)


class Notice(ApiModel):
    code: str
    severity: Literal["INFO", "WARNING", "CRITICAL"]
    message: str
    leg_id: str | None = None


class RouteSummary(ApiModel):
    standard_duration_sec: int = Field(ge=0)
    personalized_duration_sec: int = Field(ge=0)
    departure_at: datetime
    arrival_at: datetime
    total_distance_m: int = Field(ge=0)
    walk_distance_m: int = Field(ge=0)
    transfer_count: int = Field(ge=0)
    fare_krw: int = Field(ge=0)


class BaseLeg(ApiModel):
    leg_id: str
    start: PlaceInput
    end: PlaceInput
    distance_m: int = Field(ge=0)
    standard_duration_sec: int = Field(ge=0)
    personalized_duration_sec: int = Field(ge=0)
    geometry: GeoJsonLineString


class WalkStep(ApiModel):
    instruction: str
    distance_m: int = Field(ge=0)
    street_name: str | None = None
    geometry: GeoJsonLineString


class WalkLeg(BaseLeg):
    mode: Literal["WALK"] = "WALK"
    steps: list[WalkStep]
    max_slope_percent: float | None = Field(default=None, ge=0)
    has_stairs: bool
    data_confidence: DataConfidence
    data_source: DataSource = DataSource.UNKNOWN


class BusLeg(BaseLeg):
    mode: Literal["BUS"] = "BUS"
    route_id: str
    route_name: str
    boarding_stop: PlaceInput
    alighting_stop: PlaceInput
    low_floor_status: LowFloorStatus
    departure_at: datetime
    arrival_at: datetime
    time_source: TimeSource
    data_confidence: DataConfidence
    data_source: DataSource = DataSource.UNKNOWN


class StationFacility(ApiModel):
    type: Literal["ELEVATOR", "ESCALATOR", "WHEELCHAIR_LIFT", "ACCESSIBLE_TOILET"]
    status: FacilityStatus
    location_description: str | None = None
    observed_at: datetime | None = None
    data_confidence: DataConfidence
    data_source: DataSource = DataSource.UNKNOWN


class SubwayLeg(BaseLeg):
    mode: Literal["SUBWAY"] = "SUBWAY"
    line_id: str
    line_name: str
    line_color: str | None = None
    boarding_station: PlaceInput
    alighting_station: PlaceInput
    departure_at: datetime
    arrival_at: datetime
    time_source: TimeSource
    facilities: list[StationFacility]
    data_confidence: DataConfidence


class TaxiLeg(BaseLeg):
    mode: Literal["TAXI"] = "TAXI"
    expected_fare_krw: int = Field(ge=0)
    time_source: TimeSource


RouteLeg = Annotated[WalkLeg | BusLeg | SubwayLeg | TaxiLeg, Field(discriminator="mode")]


class Route(ApiModel):
    route_id: str
    rank: int = Field(ge=1)
    mode: RouteMode
    title: str
    accessibility_status: AccessibilityStatus
    data_confidence: DataConfidence
    summary: RouteSummary
    warnings: list[Notice]
    unavailable_reasons: list[Notice]
    legs: list[RouteLeg] = Field(min_length=1)


class RouteSearchRequest(ApiModel):
    origin: PlaceInput
    destination: PlaceInput
    mode: RouteMode
    departure_at: datetime | None = None


class SearchStatus(StrEnum):
    SUCCESS = "SUCCESS"
    NO_ACCESSIBLE_ROUTE = "NO_ACCESSIBLE_ROUTE"


class RouteSearchResponse(ApiModel):
    search_id: str
    mode: RouteMode
    status: SearchStatus
    generated_at: datetime
    expires_at: datetime
    routes: list[Route]
    fallback_modes: list[RouteMode]
    notices: list[Notice]


class NavigationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REROUTE_SUGGESTED = "REROUTE_SUGGESTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class RerouteReason(StrEnum):
    MISSED_TRANSIT = "MISSED_TRANSIT"
    OFF_ROUTE = "OFF_ROUTE"
    USER_REQUEST = "USER_REQUEST"


class GuidanceInstruction(ApiModel):
    instruction_id: str
    type: Literal["WALK", "BOARD", "ALIGHT", "TRANSFER", "ARRIVE"]
    message: str
    distance_to_action_m: int = Field(ge=0)
    expected_at: datetime | None = None


class RerouteSuggestion(ApiModel):
    reason: RerouteReason
    message: str
    detected_at: datetime


class NavigationSession(ApiModel):
    session_id: str
    status: NavigationStatus
    route_revision: int = Field(ge=1)
    route: Route
    started_at: datetime
    updated_at: datetime
    next_instruction: GuidanceInstruction
    reroute_suggestion: RerouteSuggestion | None = None


class LocationSample(ApiModel):
    coordinate: Coordinate
    recorded_at: datetime
    accuracy_m: float = Field(ge=0)


class NavigationUpdate(ApiModel):
    session_id: str
    status: NavigationStatus
    route_revision: int = Field(ge=1)
    updated_at: datetime
    next_instruction: GuidanceInstruction
    reroute_suggestion: RerouteSuggestion | None = None


class StartNavigationRequest(ApiModel):
    route_id: str = Field(min_length=1)


class RerouteRequest(ApiModel):
    reason: RerouteReason
    current_location: LocationSample | None = None
    current_station: PlaceInput | None = None

    @model_validator(mode="after")
    def require_location_or_station(self) -> "RerouteRequest":
        if self.current_location is None and self.current_station is None:
            raise ValueError("currentLocation or currentStation is required")
        return self
