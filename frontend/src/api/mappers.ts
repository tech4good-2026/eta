import type { Place, RouteInfo, RouteSegment, UserProfile } from "../types";
import type {
  ApiBusLeg,
  ApiNotice,
  ApiPlaceInput,
  ApiRoute,
  ApiRouteLeg,
  ApiRouteMode,
  ApiRouteSearchResponse,
  ApiStationFacility,
  ApiSubwayLeg,
  ApiUpdateProfileRequest,
  ApiUserProfile,
} from "./types";

const minutes = (seconds: number) => Math.max(1, Math.ceil(seconds / 60));

export function mapProfileFromApi(profile: ApiUserProfile): UserProfile {
  return {
    chars: [...profile.travelerTypes],
    devices: profile.mobilityAids.length ? [...profile.mobilityAids] : ["NONE"],
    avoidStairs: profile.preferences.avoidStairs,
    elevatorRequired: profile.preferences.elevatorRequired,
    lowFloorBusRequired: profile.preferences.lowFloorBusRequired,
    avoidSteepSlopes: profile.preferences.avoidSteepSlopes,
    walkingSpeedMps: profile.walkingSpeed.walkingSpeedMps,
    walkingSpeedSource: profile.walkingSpeed.walkingSpeedSource === "LEARNED" ? "LEARNED" : "CALCULATED",
    walkingSpeedSampleCount: profile.walkingSpeed.walkingSpeedSampleCount,
  };
}

export function mapProfileToApi(profile: UserProfile): ApiUpdateProfileRequest {
  return {
    travelerTypes: profile.chars as ApiUpdateProfileRequest["travelerTypes"],
    mobilityAids: profile.devices.filter((device) => device !== "NONE") as ApiUpdateProfileRequest["mobilityAids"],
    preferences: {
      avoidStairs: profile.avoidStairs,
      elevatorRequired: profile.elevatorRequired,
      lowFloorBusRequired: profile.lowFloorBusRequired,
      avoidSteepSlopes: profile.avoidSteepSlopes,
    },
  };
}

export function mapPlaceToApi(place: Place): ApiPlaceInput {
  return {
    providerPlaceId: place.id,
    name: place.name,
    address: place.addr,
    coordinate: { latitude: place.lat, longitude: place.lng },
  };
}

function mapApiPlace(place: ApiPlaceInput, tag: string): Place {
  return {
    id: place.providerPlaceId || `${place.name}-${place.coordinate.latitude}-${place.coordinate.longitude}`,
    name: place.name,
    addr: place.address || "주소 정보 없음",
    tag,
    lat: place.coordinate.latitude,
    lng: place.coordinate.longitude,
    category: "지하철역",
    phone: "",
    placeUrl: "",
  };
}

function timeSourceLabel(source: string) {
  return source === "REALTIME" ? "실시간" : source === "SCHEDULED" ? "시간표" : source === "ESTIMATED" ? "예상" : "시간 미확인";
}

function lowFloorLabel(leg: ApiBusLeg) {
  const labels = {
    CONFIRMED: "저상버스 확인",
    EXPECTED: "저상버스 예상",
    NOT_LOW_FLOOR: "일반버스",
    UNKNOWN: "저상 여부 미확인",
  } as const;
  return labels[leg.lowFloorStatus];
}

function busFacilityStatus(leg: ApiBusLeg): RouteSegment["facilityStatus"] {
  if (leg.lowFloorStatus === "NOT_LOW_FLOOR") return "UNAVAILABLE";
  if (leg.lowFloorStatus === "UNKNOWN" || leg.lowFloorStatus === "EXPECTED") return "UNKNOWN";
  return "ACCESSIBLE";
}

function subwayFacilityStatus(facilities: ApiStationFacility[]): RouteSegment["facilityStatus"] {
  if (facilities.some((facility) => facility.status === "UNAVAILABLE")) return "UNAVAILABLE";
  if (!facilities.length || facilities.some((facility) => facility.status === "UNKNOWN")) return "UNKNOWN";
  return "ACCESSIBLE";
}

function facilityLabel(facility: ApiStationFacility) {
  const names = {
    ELEVATOR: "엘리베이터",
    ESCALATOR: "에스컬레이터",
    WHEELCHAIR_LIFT: "휠체어 리프트",
    ACCESSIBLE_TOILET: "장애인 화장실",
  } as const;
  const states = { AVAILABLE: "이용 가능", UNAVAILABLE: "이용 불가", UNKNOWN: "상태 미확인" } as const;
  return `${names[facility.type]} ${states[facility.status]}`;
}

function legToSegment(leg: ApiRouteLeg): RouteSegment {
  const common = { legId: leg.legId, time: `${minutes(leg.personalizedDurationSec)}분` };
  if (leg.mode === "WALK") {
    const instructions = leg.steps.map((step) => step.instruction).filter(Boolean);
    const tags = [
      leg.hasStairs ? "계단 있음" : "계단 없음",
      leg.maxSlopePercent == null ? "경사 미확인" : `최대 경사 ${leg.maxSlopePercent}%`,
    ];
    return {
      ...common,
      mode: "walk",
      title: `${leg.start.name} → ${leg.end.name} 도보`,
      desc: instructions.join(" · ") || `${leg.distanceM}m 안전 보행 구간`,
      tags,
      facilityStatus: leg.hasStairs ? "UNAVAILABLE" : leg.maxSlopePercent != null && leg.maxSlopePercent > 5 ? "CAUTION" : "ACCESSIBLE",
    };
  }
  if (leg.mode === "BUS") {
    return {
      ...common,
      mode: "bus",
      title: `${leg.routeName} 승차`,
      desc: `${leg.boardingStop.name}에서 승차해 ${leg.alightingStop.name}에서 하차합니다.`,
      tags: [lowFloorLabel(leg), timeSourceLabel(leg.timeSource)],
      facilityStatus: busFacilityStatus(leg),
    };
  }
  if (leg.mode === "SUBWAY") {
    return {
      ...common,
      mode: "subway",
      title: `${leg.lineName} 승차`,
      desc: `${leg.boardingStation.name}에서 승차해 ${leg.alightingStation.name}에서 하차합니다.`,
      tags: [...leg.facilities.map(facilityLabel), timeSourceLabel(leg.timeSource)],
      facilityStatus: subwayFacilityStatus(leg.facilities),
    };
  }
  return {
    ...common,
    mode: "taxi",
    title: "택시 이동",
    desc: `${leg.start.name}에서 ${leg.end.name}까지 이동합니다. 예상 요금 ${leg.expectedFareKrw.toLocaleString()}원`,
    tags: [timeSourceLabel(leg.timeSource)],
    facilityStatus: "CAUTION",
  };
}

function collectMapPoints(legs: ApiRouteLeg[]) {
  const points: { lat: number; lng: number }[] = [];
  for (const leg of legs) {
    for (const coordinate of leg.geometry.coordinates) {
      if (coordinate.length < 2) continue;
      const point = { lng: coordinate[0], lat: coordinate[1] };
      const previous = points.at(-1);
      if (!previous || previous.lng !== point.lng || previous.lat !== point.lat) points.push(point);
    }
  }
  return points;
}

function collectStations(legs: ApiRouteLeg[]) {
  const stations = new Map<string, Place>();
  for (const leg of legs) {
    if (leg.mode !== "SUBWAY") continue;
    for (const station of [leg.boardingStation, leg.alightingStation]) {
      const mapped = mapApiPlace(station, "지하 GPS 보정역");
      stations.set(mapped.id, mapped);
    }
  }
  return [...stations.values()];
}

function noticeToUi(notice: ApiNotice) {
  return { warn: notice.severity !== "INFO", text: notice.message };
}

export function mapRouteFromApi(route: ApiRoute): RouteInfo {
  return {
    id: route.routeId,
    mode: route.mode.toLowerCase() as RouteInfo["mode"],
    general: minutes(route.summary.standardDurationSec),
    personal: minutes(route.summary.personalizedDurationSec),
    transfers: route.summary.transferCount,
    walk: route.summary.walkDistanceM,
    fare: route.summary.fareKrw,
    label: route.title,
    feasible: route.accessibilityStatus !== "UNAVAILABLE",
    accessibilityStatus: route.accessibilityStatus,
    notices: [...route.warnings, ...route.unavailableReasons].map(noticeToUi),
    segments: route.legs.map(legToSegment),
    mapPoints: collectMapPoints(route.legs),
    stationOptions: collectStations(route.legs),
  };
}

export function mapRouteSearchFromApi(response: ApiRouteSearchResponse) {
  return {
    status: response.status,
    routes: response.routes.map(mapRouteFromApi),
    fallbackModes: response.fallbackModes.map((mode) => mode.toLowerCase() as RouteInfo["mode"]),
    notices: response.notices.map(noticeToUi),
  };
}

export function mapModeToApi(mode: RouteInfo["mode"]): ApiRouteMode {
  return mode.toUpperCase() as ApiRouteMode;
}

export function mapSubwayStation(leg: ApiSubwayLeg, end: "boarding" | "alighting") {
  return mapApiPlace(end === "boarding" ? leg.boardingStation : leg.alightingStation, "지하 GPS 보정역");
}
