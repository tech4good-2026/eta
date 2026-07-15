import { describe, expect, it } from "vitest";

import {
  mapProfileFromApi,
  mapProfileToApi,
  mapRouteFromApi,
  mapRouteSearchFromApi,
} from "./mappers";
import type { ApiRoute, ApiUserProfile } from "./types";

const apiProfile: ApiUserProfile = {
  userId: "usr_demo_001",
  travelerTypes: ["MOBILITY_IMPAIRED"],
  mobilityAids: [],
  preferences: {
    avoidStairs: true,
    elevatorRequired: true,
    lowFloorBusRequired: false,
    avoidSteepSlopes: true,
  },
  walkingSpeed: {
    walkingSpeedMps: 0.7,
    walkingSpeedSource: "PROFILE_DEFAULT",
    walkingSpeedSampleCount: 0,
    updatedAt: "2026-07-15T09:00:00+09:00",
  },
};

const apiRoute: ApiRoute = {
  routeId: "route_001",
  rank: 1,
  mode: "TRANSIT",
  title: "저상버스 우선 경로",
  accessibilityStatus: "CAUTION",
  dataConfidence: "ESTIMATED",
  summary: {
    standardDurationSec: 1200,
    personalizedDurationSec: 1500,
    departureAt: "2026-07-15T10:00:00+09:00",
    arrivalAt: "2026-07-15T10:25:00+09:00",
    totalDistanceM: 5000,
    walkDistanceM: 320,
    transferCount: 1,
    fareKrw: 1500,
  },
  warnings: [
    { code: "LOW_FLOOR_UNKNOWN", severity: "WARNING", message: "저상버스 여부를 확인 중입니다.", legId: "leg_bus" },
  ],
  unavailableReasons: [],
  legs: [
    {
      legId: "leg_walk",
      mode: "WALK",
      start: {
        name: "서울역",
        coordinate: { latitude: 37.5547, longitude: 126.9707 },
      },
      end: {
        name: "정류장",
        coordinate: { latitude: 37.556, longitude: 126.973 },
      },
      distanceM: 320,
      standardDurationSec: 240,
      personalizedDurationSec: 360,
      geometry: {
        type: "LineString",
        coordinates: [
          [126.9707, 37.5547],
          [126.973, 37.556],
        ],
      },
      steps: [],
      maxSlopePercent: 4.2,
      hasStairs: false,
      dataConfidence: "ESTIMATED",
      dataSource: "TMAP",
    },
    {
      legId: "leg_bus",
      mode: "BUS",
      start: {
        name: "정류장",
        coordinate: { latitude: 37.556, longitude: 126.973 },
      },
      end: {
        name: "시청",
        coordinate: { latitude: 37.5663, longitude: 126.9779 },
      },
      distanceM: 4680,
      standardDurationSec: 960,
      personalizedDurationSec: 1140,
      geometry: {
        type: "LineString",
        coordinates: [
          [126.973, 37.556],
          [126.9779, 37.5663],
        ],
      },
      routeId: "100100001",
      routeName: "402",
      boardingStop: {
        name: "서울역버스환승센터",
        coordinate: { latitude: 37.556, longitude: 126.973 },
      },
      alightingStop: {
        name: "시청앞",
        coordinate: { latitude: 37.5663, longitude: 126.9779 },
      },
      lowFloorStatus: "UNKNOWN",
      departureAt: "2026-07-15T10:06:00+09:00",
      arrivalAt: "2026-07-15T10:25:00+09:00",
      timeSource: "REALTIME",
      dataConfidence: "VERIFIED",
      dataSource: "SEOUL_OPEN_DATA",
    },
  ],
};

describe("profile mappers", () => {
  it("maps PROFILE_DEFAULT to CALCULATED and empty aids to NONE", () => {
    expect(mapProfileFromApi(apiProfile)).toMatchObject({
      chars: ["MOBILITY_IMPAIRED"],
      devices: ["NONE"],
      walkingSpeedSource: "CALCULATED",
      walkingSpeedMps: 0.7,
    });
  });

  it("removes the UI-only NONE value before PUT", () => {
    const ui = mapProfileFromApi(apiProfile);
    expect(mapProfileToApi({ ...ui, devices: ["NONE"] })).toEqual({
      travelerTypes: ["MOBILITY_IMPAIRED"],
      mobilityAids: [],
      preferences: {
        avoidStairs: true,
        elevatorRequired: true,
        lowFloorBusRequired: false,
        avoidSteepSlopes: true,
      },
    });
  });
});

describe("route mappers", () => {
  it("maps GeoJSON [longitude, latitude] and detailed legs to the existing UI model", () => {
    const route = mapRouteFromApi(apiRoute);

    expect(route).toMatchObject({
      id: "route_001",
      mode: "transit",
      general: 20,
      personal: 25,
      accessibilityStatus: "CAUTION",
      mapPoints: [
        { lng: 126.9707, lat: 37.5547 },
        { lng: 126.973, lat: 37.556 },
        { lng: 126.9779, lat: 37.5663 },
      ],
    });
    expect(route.segments[1]).toMatchObject({
      mode: "bus",
      title: "402 승차",
      facilityStatus: "UNKNOWN",
      tags: ["저상 여부 미확인", "실시간"],
    });
  });

  it("keeps NO_ACCESSIBLE_ROUTE as an empty normal result without a mock fallback", () => {
    expect(
      mapRouteSearchFromApi({
        searchId: "search_001",
        mode: "TRANSIT",
        status: "NO_ACCESSIBLE_ROUTE",
        generatedAt: "2026-07-15T10:00:00+09:00",
        expiresAt: "2026-07-15T10:10:00+09:00",
        routes: [],
        fallbackModes: ["TAXI"],
        notices: [],
      }),
    ).toEqual({ status: "NO_ACCESSIBLE_ROUTE", routes: [], fallbackModes: ["taxi"], notices: [] });
  });
});
