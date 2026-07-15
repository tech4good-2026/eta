import { describe, expect, it } from "vitest";

import { createCurrentLocationPlace, getCurrentCoordinates } from "./currentLocation";

describe("current location utilities", () => {
  it("converts a successful browser position into app coordinates", async () => {
    const geolocation = {
      getCurrentPosition(success: PositionCallback) {
        success({
          coords: { latitude: 37.5, longitude: 127 },
        } as GeolocationPosition);
      },
    } as Geolocation;

    await expect(getCurrentCoordinates(geolocation)).resolves.toEqual({
      lat: 37.5,
      lng: 127,
    });
  });

  it("creates the current GPS place used as a route origin", () => {
    expect(createCurrentLocationPlace({ lat: 37.5, lng: 127 })).toMatchObject({
      id: "current-gps",
      name: "나의 현위치 (GPS)",
      lat: 37.5,
      lng: 127,
    });
  });
});
