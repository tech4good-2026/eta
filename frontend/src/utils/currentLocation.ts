import type { Place } from "../types";

export interface Coordinates {
  lat: number;
  lng: number;
}

export function getCurrentCoordinates(
  geolocation: Geolocation | undefined,
): Promise<Coordinates> {
  if (!geolocation) {
    return Promise.reject(new Error("GEOLOCATION_UNAVAILABLE"));
  }

  return new Promise((resolve, reject) => {
    geolocation.getCurrentPosition(
      (position) => {
        resolve({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        });
      },
      reject,
    );
  });
}

export function createCurrentLocationPlace(coords: Coordinates): Place {
  return {
    id: "current-gps",
    name: "나의 현위치 (GPS)",
    addr: "GPS로 수신한 현재 실시간 좌표",
    tag: "현재 수신지점",
    lat: coords.lat,
    lng: coords.lng,
    category: "현위치",
    phone: "없음",
    placeUrl: "",
  };
}
