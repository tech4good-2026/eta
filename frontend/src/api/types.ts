export type ApiTravelerType =
  | "PREGNANT"
  | "SENIOR"
  | "MOBILITY_IMPAIRED"
  | "TEMPORARILY_INJURED"
  | "CAREGIVER_WITH_CHILD"
  | "OTHER";

export type ApiMobilityAid =
  | "MANUAL_WHEELCHAIR"
  | "POWER_WHEELCHAIR"
  | "STROLLER"
  | "CANE"
  | "CRUTCHES"
  | "WALKER";

export type ApiRouteMode = "TRANSIT" | "TAXI" | "WALK";
export type ApiAccessibilityStatus = "ACCESSIBLE" | "CAUTION" | "UNAVAILABLE";
export type ApiDataConfidence = "VERIFIED" | "ESTIMATED" | "UNKNOWN";
export type ApiTimeSource = "REALTIME" | "SCHEDULED" | "ESTIMATED" | "UNKNOWN";
export type ApiDataSource =
  | "TMAP"
  | "SEOUL_OPEN_DATA"
  | "WALKWAY_OPEN_DATA"
  | "SYNTHETIC_FIXTURE"
  | "TEAM_ENGINE"
  | "UNKNOWN";

export interface ApiCoordinate {
  latitude: number;
  longitude: number;
}

export interface ApiPlaceInput {
  providerPlaceId?: string | null;
  name: string;
  address?: string | null;
  coordinate: ApiCoordinate;
}

export interface ApiProfilePreferences {
  avoidStairs: boolean;
  elevatorRequired: boolean;
  lowFloorBusRequired: boolean;
  avoidSteepSlopes: boolean;
}

export interface ApiWalkingSpeedProfile {
  walkingSpeedMps: number;
  walkingSpeedSource: string;
  walkingSpeedSampleCount: number;
  updatedAt: string;
  baseSpeedMps?: number;
  maxSpeedMps?: number;
}

export interface ApiUserProfile {
  userId: string;
  travelerTypes: ApiTravelerType[];
  mobilityAids: ApiMobilityAid[];
  preferences: ApiProfilePreferences;
  walkingSpeed: ApiWalkingSpeedProfile;
}

export interface ApiUpdateProfileRequest {
  travelerTypes: ApiTravelerType[];
  mobilityAids: ApiMobilityAid[];
  preferences: ApiProfilePreferences;
}

export interface ApiNotice {
  code: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  message: string;
  legId?: string | null;
}

export interface ApiGeoJsonLineString {
  type: "LineString";
  coordinates: number[][];
}

interface ApiBaseLeg {
  legId: string;
  start: ApiPlaceInput;
  end: ApiPlaceInput;
  distanceM: number;
  standardDurationSec: number;
  personalizedDurationSec: number;
  geometry: ApiGeoJsonLineString;
}

export interface ApiWalkStep {
  instruction: string;
  distanceM: number;
  streetName?: string | null;
  geometry: ApiGeoJsonLineString;
}

export type ApiSurfaceType =
  | "ASPHALT"
  | "CONCRETE"
  | "BLOCK"
  | "STONE"
  | "BRICK"
  | "UNPAVED"
  | "UNKNOWN";

export interface ApiWalkLeg extends ApiBaseLeg {
  mode: "WALK";
  steps: ApiWalkStep[];
  maxSlopePercent?: number | null;
  hasStairs: boolean;
  surfaceType?: ApiSurfaceType | null;
  widthM?: number | null;
  curbRampPresent?: boolean | null;
  tactilePavingPresent?: boolean | null;
  passable?: boolean;
  dataConfidence: ApiDataConfidence;
  dataSource: ApiDataSource;
}

export interface ApiBusLeg extends ApiBaseLeg {
  mode: "BUS";
  routeId: string;
  routeName: string;
  boardingStop: ApiPlaceInput;
  alightingStop: ApiPlaceInput;
  lowFloorStatus: "CONFIRMED" | "EXPECTED" | "NOT_LOW_FLOOR" | "UNKNOWN";
  departureAt: string;
  arrivalAt: string;
  timeSource: ApiTimeSource;
  dataConfidence: ApiDataConfidence;
  dataSource: ApiDataSource;
}

export interface ApiStationFacility {
  type: "ELEVATOR" | "ESCALATOR" | "WHEELCHAIR_LIFT" | "ACCESSIBLE_TOILET";
  status: "AVAILABLE" | "UNAVAILABLE" | "UNKNOWN";
  locationDescription?: string | null;
  observedAt?: string | null;
  dataConfidence: ApiDataConfidence;
  dataSource: ApiDataSource;
}

export interface ApiSubwayLeg extends ApiBaseLeg {
  mode: "SUBWAY";
  lineId: string;
  lineName: string;
  lineColor?: string | null;
  boardingStation: ApiPlaceInput;
  alightingStation: ApiPlaceInput;
  departureAt: string;
  arrivalAt: string;
  timeSource: ApiTimeSource;
  facilities: ApiStationFacility[];
  dataConfidence: ApiDataConfidence;
}

export interface ApiTaxiLeg extends ApiBaseLeg {
  mode: "TAXI";
  expectedFareKrw: number;
  timeSource: ApiTimeSource;
}

export type ApiRouteLeg = ApiWalkLeg | ApiBusLeg | ApiSubwayLeg | ApiTaxiLeg;

export interface ApiRoute {
  routeId: string;
  rank: number;
  mode: ApiRouteMode;
  title: string;
  accessibilityStatus: ApiAccessibilityStatus;
  dataConfidence: ApiDataConfidence;
  summary: {
    standardDurationSec: number;
    personalizedDurationSec: number;
    departureAt: string;
    arrivalAt: string;
    totalDistanceM: number;
    walkDistanceM: number;
    transferCount: number;
    fareKrw: number;
  };
  warnings: ApiNotice[];
  unavailableReasons: ApiNotice[];
  legs: ApiRouteLeg[];
}

export interface ApiRouteSearchRequest {
  origin: ApiPlaceInput;
  destination: ApiPlaceInput;
  mode: ApiRouteMode;
  departureAt?: string;
}

export interface ApiRouteSearchResponse {
  searchId: string;
  mode: ApiRouteMode;
  status: "SUCCESS" | "NO_ACCESSIBLE_ROUTE";
  generatedAt: string;
  expiresAt: string;
  routes: ApiRoute[];
  fallbackModes: ApiRouteMode[];
  notices: ApiNotice[];
}

export type ApiNavigationStatus = "ACTIVE" | "REROUTE_SUGGESTED" | "COMPLETED" | "CANCELLED";
export type ApiRerouteReason = "MISSED_TRANSIT" | "OFF_ROUTE" | "USER_REQUEST";

export interface ApiGuidanceInstruction {
  instructionId: string;
  type: "WALK" | "BOARD" | "ALIGHT" | "TRANSFER" | "ARRIVE";
  message: string;
  distanceToActionM: number;
  expectedAt?: string | null;
}

export interface ApiRerouteSuggestion {
  reason: ApiRerouteReason;
  message: string;
  detectedAt: string;
}

export interface ApiNavigationSession {
  sessionId: string;
  status: ApiNavigationStatus;
  routeRevision: number;
  route: ApiRoute;
  startedAt: string;
  updatedAt: string;
  nextInstruction: ApiGuidanceInstruction;
  rerouteSuggestion?: ApiRerouteSuggestion | null;
}

export interface ApiNavigationUpdate {
  sessionId: string;
  status: ApiNavigationStatus;
  routeRevision: number;
  updatedAt: string;
  nextInstruction: ApiGuidanceInstruction;
  rerouteSuggestion?: ApiRerouteSuggestion | null;
}

export interface ApiLocationSample {
  coordinate: ApiCoordinate;
  recordedAt: string;
  accuracyM: number;
}

export interface ApiRerouteRequest {
  reason: ApiRerouteReason;
  currentLocation?: ApiLocationSample;
  currentStation?: ApiPlaceInput;
}

export interface ApiNavigationCompletion {
  sessionId: string;
  status: "COMPLETED";
  routeRevision: number;
  completedAt: string;
  walkingSpeedUpdated: boolean;
  walkingSpeed: ApiWalkingSpeedProfile;
}

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    requestId?: string;
    details?: unknown;
  };
}
