import { describe, expect, it } from "vitest";

import { isKakaoSdkReady, shouldStopWaitingForKakao } from "./kakaoSdk";

describe("Kakao SDK readiness", () => {
  it("recognizes a loaded Maps SDK", () => {
    expect(isKakaoSdkReady({ maps: { Map: function Map() {} } })).toBe(true);
    expect(isKakaoSdkReady(undefined)).toBe(false);
  });

  it("stops the loading state after five seconds", () => {
    expect(shouldStopWaitingForKakao(1000, 5999)).toBe(false);
    expect(shouldStopWaitingForKakao(1000, 6000)).toBe(true);
  });
});
