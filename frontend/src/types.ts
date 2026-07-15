/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export interface UserProfile {
  chars: string[]; // TravelerType codes: PREGNANT, SENIOR, MOBILITY_IMPAIRED, TEMPORARILY_INJURED, CAREGIVER_WITH_CHILD, OTHER
  devices: string[]; // MobilityAid codes: MANUAL_WHEELCHAIR, POWER_WHEELCHAIR, STROLLER, CANE, CRUTCHES, WALKER, NONE
  avoidStairs: boolean;
  elevatorRequired: boolean;
  lowFloorBusRequired: boolean;
  avoidSteepSlopes: boolean;
  walkingSpeedMps: number;
  walkingSpeedSource: "CALCULATED" | "LEARNED";
  walkingSpeedSampleCount: number;
}

export interface Place {
  id: string;
  name: string;
  addr: string;
  tag: string;
  lat: number;
  lng: number;
  category: string;
  phone: string;
  placeUrl: string;
}

export interface RouteSegment {
  legId?: string;
  mode: "walk" | "bus" | "subway" | "taxi";
  title: string;
  desc: string;
  time: string;
  tags?: string[];
  facilityStatus?: "ACCESSIBLE" | "CAUTION" | "UNAVAILABLE" | "UNKNOWN";
}

export interface RouteNotice {
  warn: boolean;
  text: string;
}

export interface RouteInfo {
  id: string;
  mode: "transit" | "taxi" | "walk";
  general: number; // general duration in minutes
  personal: number; // custom duration in minutes
  transfers: number;
  walk: number; // walk distance in meters
  fare: number;
  label: string;
  feasible: boolean;
  accessibilityStatus: "ACCESSIBLE" | "CAUTION" | "UNAVAILABLE";
  notices: RouteNotice[];
  segments: RouteSegment[];
  mapPoints: { lat: number; lng: number }[];
  mapSegments: { mode: RouteSegment["mode"]; points: { lat: number; lng: number }[] }[];
  stationOptions: Place[];
}

export const CHAR_OPTIONS = [
  { code: "PREGNANT", label: "임산부" },
  { code: "SENIOR", label: "고령자" },
  { code: "MOBILITY_IMPAIRED", label: "지체·이동 제약 사용자" },
  { code: "TEMPORARILY_INJURED", label: "일시적 부상자" },
  { code: "CAREGIVER_WITH_CHILD", label: "영유아 동반자" },
  { code: "OTHER", label: "기타" }
];

export const DEVICE_OPTIONS = [
  { code: "MANUAL_WHEELCHAIR", label: "수동 휠체어" },
  { code: "POWER_WHEELCHAIR", label: "전동 휠체어" },
  { code: "STROLLER", label: "유모차" },
  { code: "CANE", label: "지팡이" },
  { code: "CRUTCHES", label: "목발" },
  { code: "WALKER", label: "보행 보조기" },
  { code: "NONE", label: "없음" }
];
