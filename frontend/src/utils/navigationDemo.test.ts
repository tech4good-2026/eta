import { describe, expect, it } from "vitest";

import { createDemoOffRouteCoordinate } from "./navigationDemo";

describe("createDemoOffRouteCoordinate", () => {
  it("creates a nearby perpendicular point instead of leaving the Seoul demo area", () => {
    const coordinate = createDemoOffRouteCoordinate(
      [
        { lat: 37.5547, lng: 126.9707 },
        { lat: 37.5663, lng: 126.9779 },
      ],
      { lat: 37.5547, lng: 126.9707 },
    );

    expect(Math.abs(coordinate.latitude - 37.5547)).toBeLessThan(0.003);
    expect(Math.abs(coordinate.longitude - 126.9707)).toBeLessThan(0.003);
    expect(coordinate.latitude).not.toBe(37.5547);
    expect(coordinate.longitude).not.toBe(126.9707);
  });
});
