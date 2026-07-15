import { afterEach, describe, expect, it, vi } from "vitest";

import { createCurrentLocationPlace, getCurrentCoordinates } from "./currentLocation";

describe("current location utilities", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("converts a successful browser position into app coordinates", async () => {
    const geolocation = {
      getCurrentPosition(success: PositionCallback) {
        success({
          coords: { latitude: 37.5, longitude: 127 },
        } as GeolocationPosition);
      },
    } as unknown as Geolocation;

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

  it("rejects when the browser never answers the location request", async () => {
    vi.useFakeTimers();
    const geolocation = {
      getCurrentPosition() {
        // Simulates an embedded browser that never calls success or error.
      },
    } as unknown as Geolocation;

    const resultPromise = Promise.race([
      getCurrentCoordinates(geolocation, 1_000).then(
        () => "RESOLVED",
        (error: Error) => error.message,
      ),
      new Promise<string>((resolve) => {
        setTimeout(() => resolve("STILL_PENDING"), 2_000);
      }),
    ]);

    await vi.advanceTimersByTimeAsync(2_000);

    await expect(resultPromise).resolves.toBe("GEOLOCATION_TIMEOUT");
  });
});
