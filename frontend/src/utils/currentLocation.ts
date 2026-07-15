import type { Place } from "../types";

export interface Coordinates {
  lat: number;
  lng: number;
}

export const DEFAULT_GEOLOCATION_TIMEOUT_MS = 8_000;

export function getCurrentCoordinates(
  geolocation: Geolocation | undefined,
  timeoutMs = DEFAULT_GEOLOCATION_TIMEOUT_MS,
): Promise<Coordinates> {
  if (!geolocation) {
    return Promise.reject(new Error("GEOLOCATION_UNAVAILABLE"));
  }

  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (callback: () => void) => {
      if (settled) return;
      settled = true;
      globalThis.clearTimeout(timeoutId);
      callback();
    };
    const timeoutId = globalThis.setTimeout(() => {
      finish(() => reject(new Error("GEOLOCATION_TIMEOUT")));
    }, timeoutMs);

    try {
      geolocation.getCurrentPosition(
        (position) => {
          finish(() => {
            resolve({
              lat: position.coords.latitude,
              lng: position.coords.longitude,
            });
          });
        },
        (error) => finish(() => reject(error)),
        {
          enableHighAccuracy: true,
          timeout: timeoutMs,
          maximumAge: 30_000,
        },
      );
    } catch (error) {
      finish(() => reject(error));
    }
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
