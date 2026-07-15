import type { Place } from "../types";

export interface KakaoPlaceDocument {
  id: string;
  place_name: string;
  address_name: string;
  road_address_name: string;
  category_group_name: string;
  category_name: string;
  phone: string;
  place_url: string;
  x: string;
  y: string;
}

export function mapKakaoPlace(place: KakaoPlaceDocument): Place {
  return {
    id: place.id,
    name: place.place_name,
    addr: place.road_address_name || place.address_name || "주소 정보 없음",
    tag: "카카오 장소 검색",
    lat: Number(place.y),
    lng: Number(place.x),
    category: place.category_group_name || place.category_name.split(" > ").at(-1) || "장소",
    phone: place.phone || "",
    placeUrl: place.place_url || "",
  };
}

export async function searchKakaoPlaces(query: string): Promise<Place[]> {
  if (query.trim().length < 2) return [];
  const kakao = window.kakao;
  if (!kakao?.maps?.services?.Places) {
    throw new Error("KAKAO_SDK_NOT_READY");
  }

  return new Promise((resolve, reject) => {
    const places = new kakao.maps.services.Places();
    places.keywordSearch(query.trim(), (documents: KakaoPlaceDocument[], status: string) => {
      if (status === kakao.maps.services.Status.OK) {
        resolve(documents.map(mapKakaoPlace));
      } else if (status === kakao.maps.services.Status.ZERO_RESULT) {
        resolve([]);
      } else {
        reject(new Error("KAKAO_PLACE_SEARCH_FAILED"));
      }
    });
  });
}
