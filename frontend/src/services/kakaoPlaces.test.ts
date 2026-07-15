import { describe, expect, it } from "vitest";

import { mapKakaoPlace } from "./kakaoPlaces";

describe("mapKakaoPlace", () => {
  it("maps Kakao coordinates and prefers a road address", () => {
    expect(
      mapKakaoPlace({
        id: "123",
        place_name: "서울역",
        address_name: "서울 용산구 동자동 43-205",
        road_address_name: "서울 용산구 한강대로 405",
        category_group_name: "지하철역",
        category_name: "교통 > 철도 > 기차역",
        phone: "1544-7788",
        place_url: "https://place.map.kakao.com/123",
        x: "126.9707",
        y: "37.5547",
      }),
    ).toEqual({
      id: "123",
      name: "서울역",
      addr: "서울 용산구 한강대로 405",
      tag: "카카오 장소 검색",
      lat: 37.5547,
      lng: 126.9707,
      category: "지하철역",
      phone: "1544-7788",
      placeUrl: "https://place.map.kakao.com/123",
    });
  });
});
