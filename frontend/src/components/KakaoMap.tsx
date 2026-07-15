import React, { useEffect, useRef, useState } from "react";
import { isKakaoSdkReady, KAKAO_SDK_TIMEOUT_MS, shouldStopWaitingForKakao } from "../services/kakaoSdk";

interface MapMarker {
  lat: number;
  lng: number;
  title?: string;
  type?: "you" | "origin" | "dest" | "elevator";
}

type RouteMode = "walk" | "bus" | "subway" | "taxi";

interface RouteSegmentPath {
  mode: RouteMode;
  points: { lat: number; lng: number }[];
}

// 지도 경로선 모드별 색상/선 스타일 (단계 목록의 칩 색상과 일치).
const LINE_META: Record<RouteMode, { color: string; style: string }> = {
  walk: { color: "#059669", style: "shortdash" },
  bus: { color: "#2563EB", style: "solid" },
  subway: { color: "#7C3AED", style: "solid" },
  taxi: { color: "#D97706", style: "solid" },
};

interface KakaoMapProps {
  center: { lat: number; lng: number };
  level?: number;
  markers?: MapMarker[];
  routePath?: { lat: number; lng: number }[];
  routeSegments?: RouteSegmentPath[];
  height?: string;
}

// Global declaration for TS environment
declare global {
  interface Window {
    kakao: any;
  }
}

export function KakaoMap({
  center,
  level = 4,
  markers = [],
  routePath = [],
  routeSegments = [],
  height = "100%",
}: KakaoMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const overlayListRef = useRef<any[]>([]);
  const polylinesRef = useRef<any[]>([]);
  const [isMapApiReady, setIsMapApiReady] = useState(false);
  const [mapLoadFailed, setMapLoadFailed] = useState(false);

  // Check if SDK has loaded
  useEffect(() => {
    let active = true;
    const startedAt = Date.now();
    const failTimer = window.setTimeout(() => {
      if (active && shouldStopWaitingForKakao(startedAt, Date.now())) setMapLoadFailed(true);
    }, KAKAO_SDK_TIMEOUT_MS);
    const markReady = () => {
      if (!active) return;
      window.clearTimeout(failTimer);
      setMapLoadFailed(false);
      setIsMapApiReady(true);
    };
    const checkKakao = () => {
      if (!active) return;
      if (window.kakao?.maps) {
        if (isKakaoSdkReady(window.kakao)) {
           markReady();
        } else if (typeof window.kakao.maps.load === "function") {
           window.kakao.maps.load(markReady);
        }
      } else {
        window.setTimeout(checkKakao, 50);
      }
    };
    checkKakao();
    return () => {
      active = false;
      window.clearTimeout(failTimer);
    };
  }, []);

  // Initialize and Update Map
  useEffect(() => {
    if (!isMapApiReady || !containerRef.current) return;

    const { maps } = window.kakao;
    if (!maps || !maps.Map) return;

    // 1. Create Map Instance if not existing
    if (!mapRef.current) {
      const options = {
        center: new maps.LatLng(center.lat, center.lng),
        level: level,
      };
      const map = new maps.Map(containerRef.current, options);
      mapRef.current = map;

      // Prevent map pinch/zoom conflicts with scroll containers inside app
      map.setZoomable(true);
    } else {
      // Just move center
      const latlng = new maps.LatLng(center.lat, center.lng);
      mapRef.current.setCenter(latlng);
      mapRef.current.setLevel(level);
    }

    const map = mapRef.current;

    // 2. Clear old overlays and markers
    overlayListRef.current.forEach((overlay) => overlay.setMap(null));
    overlayListRef.current = [];

    polylinesRef.current.forEach((line) => line.setMap(null));
    polylinesRef.current = [];

    // 3. Render Custom Markers
    const bounds = new maps.LatLngBounds();
    let hasPins = false;

    markers.forEach((marker) => {
      const position = new maps.LatLng(marker.lat, marker.lng);
      bounds.extend(position);
      hasPins = true;

      // 라벨을 핀 위에 두고, 핀 뾰족한 끝(하단)이 실제 좌표에 오도록 bottom-center로 앵커링.
      let contentHtml = "";
      if (marker.type === "origin") {
        contentHtml = `
          <div class="pin origin select-none pointer-events-none flex flex-col items-center">
            <div class="bg-[#2563EB] text-white text-[10px] font-bold px-1.5 py-0.5 rounded shadow mb-1 whitespace-nowrap">${marker.title || "출발지"}</div>
            <div class="pin-badge w-[30px] h-[30px] rounded-[50%_50%_50%_4px] rotate-45 flex items-center justify-center bg-[#2563EB] shadow-[0_1px_2px_rgba(15,23,42,.08)]">
              <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" class="-rotate-45 w-[14px] h-[14px]">
                <circle cx="12" cy="12" r="3"/>
              </svg>
            </div>
          </div>`;
      } else if (marker.type === "dest") {
        contentHtml = `
          <div class="pin dest select-none pointer-events-none flex flex-col items-center">
            <div class="bg-[#F97316] text-white text-[10px] font-bold px-1.5 py-0.5 rounded shadow mb-1 whitespace-nowrap">${marker.title || "목적지"}</div>
            <div class="pin-badge w-[30px] h-[30px] rounded-[50%_50%_50%_4px] rotate-45 flex items-center justify-center bg-[#F97316] shadow-[0_1px_2px_rgba(15,23,42,.08)]">
              <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" class="-rotate-45 w-[14px] h-[14px]">
                <path d="M12 21s-7-6.5-7-11.5A7 7 0 0119 9.5C19 14.5 12 21 12 21z"/>
              </svg>
            </div>
          </div>`;
      } else if (marker.type === "elevator") {
        contentHtml = `
          <div class="pin elevator select-none pointer-events-none flex flex-col items-center">
            <div class="w-[24px] h-[24px] rounded-full bg-white border-2 border-emerald-500 flex items-center justify-center text-[9px] font-black text-emerald-600 shadow">EV</div>
            <div class="bg-emerald-600 text-white text-[9px] font-bold px-1 py-0.5 rounded shadow mt-0.5 whitespace-nowrap">${marker.title || "엘리베이터"}</div>
          </div>`;
      } else if (marker.type === "you") {
        contentHtml = `
          <div class="pin you select-none pointer-events-none flex flex-col items-center">
            <div class="bg-[#3B82F6] text-white text-[10px] font-bold px-1.5 py-0.5 rounded shadow mb-1 whitespace-nowrap">나의 위치</div>
            <div class="pin-badge w-[30px] h-[30px] rounded-[50%_50%_50%_4px] rotate-45 flex items-center justify-center bg-white border-3 border-[#3B82F6] shadow-[0_1px_2px_rgba(15,23,42,.08)]">
              <svg viewBox="0 0 24 24" fill="none" stroke="#3B82F6" stroke-width="2.4" class="-rotate-45 w-[14px] h-[14px]">
                <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm1 14h-2v-2h2zm0-4h-2V7h2z"/>
              </svg>
            </div>
          </div>`;
      }

      const customOverlay = new maps.CustomOverlay({
        position: position,
        content: contentHtml,
        xAnchor: 0.5,
        yAnchor: 1.0,
      });

      customOverlay.setMap(map);
      overlayListRef.current.push(customOverlay);
    });

    // 4. Render Route Polylines. 세그먼트가 있으면 모드별 색상으로 나눠 그린다.
    const drawLine = (
      points: { lat: number; lng: number }[],
      color: string,
      style: string,
    ) => {
      if (!points || points.length < 2) return;
      const linePath = points.map((pt) => {
        const pos = new maps.LatLng(pt.lat, pt.lng);
        bounds.extend(pos);
        hasPins = true;
        return pos;
      });
      const polyline = new maps.Polyline({
        path: linePath,
        strokeWeight: 5,
        strokeColor: color,
        strokeOpacity: 0.9,
        strokeStyle: style,
      });
      polyline.setMap(map);
      polylinesRef.current.push(polyline);
    };

    if (routeSegments && routeSegments.length > 0) {
      routeSegments.forEach((segment) => {
        const meta = LINE_META[segment.mode];
        drawLine(segment.points, meta.color, meta.style);
      });
    } else if (routePath && routePath.length > 0) {
      drawLine(routePath, "#2563EB", "solid");
    }

    // 5. Fit bounds if there are markers or paths
    if (hasPins && markers.length > 1) {
      map.setBounds(bounds);
    }
  }, [isMapApiReady, center, level, markers, routePath, routeSegments]);

  return (
    <div className="relative w-full overflow-hidden" style={{ height }}>
      {!isMapApiReady && (
        <div className="absolute inset-0 bg-[#F1F5F9] flex flex-col items-center justify-center gap-2 z-10">
          {mapLoadFailed ? (
            <>
              <div className="w-8 h-8 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center font-black">!</div>
              <p className="text-[12px] text-[#475569] font-medium font-sans">카카오 지도를 불러오지 못했습니다.</p>
              <p className="text-[10px] text-slate-400">JavaScript 키와 허용 도메인을 확인해 주세요.</p>
            </>
          ) : (
            <>
              <div className="w-8 h-8 border-4 border-[#2563EB] border-t-transparent rounded-full animate-spin"></div>
              <p className="text-[12px] text-[#475569] font-medium font-sans">카카오 지도 데이터를 구성하고 있습니다...</p>
            </>
          )}
        </div>
      )}
      <div ref={containerRef} className="w-full h-full" id="kakao-map-container" />
    </div>
  );
}
