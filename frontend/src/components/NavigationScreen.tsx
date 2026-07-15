import React, { useEffect, useRef, useState } from "react";
import { AlertTriangle, ChevronRight, Layers, MapPin } from "lucide-react";

import { api, ApiClientError } from "../api/client";
import { mapPlaceToApi, mapRouteFromApi } from "../api/mappers";
import type {
  ApiLocationSample,
  ApiNavigationSession,
  ApiNavigationUpdate,
  ApiRerouteReason,
} from "../api/types";
import type { Place, RouteInfo } from "../types";
import { createDemoOffRouteCoordinate } from "../utils/navigationDemo";
import { KakaoMap } from "./KakaoMap";
import { PaceBar } from "./PaceBar";

interface NavigationScreenProps {
  session: ApiNavigationSession;
  origin: Place;
  destination: Place;
  speedFactor: number;
  onRouteChange: (session: ApiNavigationSession, route: RouteInfo) => void;
  onFinish: (sessionId: string) => Promise<void>;
  showToast: (msg: string) => void;
}

const delay = (milliseconds: number) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

export function NavigationScreen({
  session: initialSession,
  origin,
  destination,
  speedFactor,
  onRouteChange,
  onFinish,
  showToast,
}: NavigationScreenProps) {
  const [session, setSession] = useState<ApiNavigationSession>(initialSession);
  const [route, setRoute] = useState<RouteInfo>(() => mapRouteFromApi(initialSession.route));
  const [navIndex, setNavIndex] = useState(0);
  const [gpsIndicator, setGpsIndicator] = useState("수신 대기 중");
  const [gpsPulse, setGpsPulse] = useState(false);
  const [currentStation, setCurrentStation] = useState<Place | null>(null);
  const [rerouteSuggestion, setRerouteSuggestion] = useState<ApiNavigationUpdate["rerouteSuggestion"]>(
    initialSession.rerouteSuggestion,
  );
  const [busy, setBusy] = useState(false);
  const simulatingRef = useRef(false);
  const latestSampleRef = useRef<ApiLocationSample>({
    coordinate: { latitude: origin.lat, longitude: origin.lng },
    recordedAt: initialSession.updatedAt,
    accuracyM: 10,
  });

  const applyUpdate = (update: ApiNavigationUpdate) => {
    setSession((current) => ({
      ...current,
      status: update.status,
      routeRevision: update.routeRevision,
      updatedAt: update.updatedAt,
      nextInstruction: update.nextInstruction,
      rerouteSuggestion: update.rerouteSuggestion,
    }));
    setRerouteSuggestion(update.rerouteSuggestion);
  };

  const showApiError = (error: unknown) => {
    const message = error instanceof ApiClientError ? `${error.message} (${error.code})` : "안내 요청을 처리하지 못했습니다.";
    showToast(message);
  };

  const sendPosition = async (sample: ApiLocationSample) => {
    latestSampleRef.current = sample;
    const update = await api.sendPosition(session.sessionId, sample);
    applyUpdate(update);
    setGpsPulse(true);
    setGpsIndicator(`정밀 좌표 전송 완료 (오차: ${sample.accuracyM.toFixed(1)}m) - 기록 즉시 폐기됨`);
    window.setTimeout(() => setGpsPulse(false), 800);
    return update;
  };

  useEffect(() => {
    if (!navigator.geolocation) {
      setGpsIndicator("브라우저 위치 기능을 사용할 수 없습니다.");
      return;
    }

    const transmit = () => {
      if (simulatingRef.current) return;
      navigator.geolocation.getCurrentPosition(
        (position) => {
          void sendPosition({
            coordinate: { latitude: position.coords.latitude, longitude: position.coords.longitude },
            recordedAt: new Date(position.timestamp || Date.now()).toISOString(),
            accuracyM: position.coords.accuracy,
          }).catch(showApiError);
        },
        () => setGpsIndicator("위치 권한이 없어 수동 보정 기능만 사용합니다."),
        { enableHighAccuracy: true, maximumAge: 4000, timeout: 4000 },
      );
    };

    const intervalId = window.setInterval(transmit, 5000);
    return () => window.clearInterval(intervalId);
  }, [session.sessionId]);

  const applyReroutedSession = (nextSession: ApiNavigationSession) => {
    const nextRoute = mapRouteFromApi(nextSession.route);
    setSession(nextSession);
    setRoute(nextRoute);
    setNavIndex(0);
    setRerouteSuggestion(null);
    onRouteChange(nextSession, nextRoute);
    showToast(`새 안전 경로 갱신 완료(routeRevision=${nextSession.routeRevision})`);
  };

  const reroute = async (reason: ApiRerouteReason, station?: Place) => {
    setBusy(true);
    try {
      const nextSession = await api.rerouteNavigation(session.sessionId, {
        reason,
        ...(station
          ? { currentStation: mapPlaceToApi(station) }
          : { currentLocation: latestSampleRef.current }),
      });
      applyReroutedSession(nextSession);
    } catch (error) {
      showApiError(error);
    } finally {
      setBusy(false);
    }
  };

  const handleNextStep = async () => {
    if (navIndex + 1 >= route.segments.length) {
      setBusy(true);
      try {
        await onFinish(session.sessionId);
      } catch (error) {
        showApiError(error);
        setBusy(false);
      }
      return;
    }
    setNavIndex((index) => index + 1);
  };

  const handleMissedTransit = async () => {
    const station = currentStation || route.stationOptions[0];
    await reroute("MISSED_TRANSIT", station);
  };

  const handleStationSnap = async (station: Place) => {
    setCurrentStation(station);
    setGpsIndicator(`지하 역사 보완 수동 연동: [${station.name}] 잠금 고정됨`);
    await reroute("USER_REQUEST", station);
  };

  const triggerMockDeviation = async () => {
    if (busy) return;
    setBusy(true);
    simulatingRef.current = true;
    try {
      const previousTime = new Date(latestSampleRef.current.recordedAt).getTime();
      const firstTime = Math.max(Date.now(), previousTime + 5000);
      const coordinate = createDemoOffRouteCoordinate(route.mapPoints, origin);
      const first = await sendPosition({ coordinate, recordedAt: new Date(firstTime).toISOString(), accuracyM: 5 });
      setGpsIndicator("가상 이탈 1차 위치 전송 완료 · 5초 후 재확인");
      if (first.status !== "REROUTE_SUGGESTED") {
        await delay(5000);
        const second = await sendPosition({
          coordinate,
          recordedAt: new Date(firstTime + 5000).toISOString(),
          accuracyM: 5,
        });
        if (second.status === "REROUTE_SUGGESTED") {
          showToast("서버가 실제 위치 표본으로 경로 이탈을 감지했습니다. (REROUTE_SUGGESTED)");
        }
      }
    } catch (error) {
      showApiError(error);
    } finally {
      simulatingRef.current = false;
      setBusy(false);
    }
  };

  const navSteps = route.segments;
  const currentStep = navSteps[navIndex];

  return (
    <div className="flex-1 flex flex-col" id="view-navigation-screen">
      <div className="bg-slate-900 text-white px-5 py-3.5 flex justify-between items-center shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping"></span>
          <span className="text-[12px] font-black text-emerald-400">STATUS: {session.status}</span>
        </div>
        <div className="flex items-center gap-3 text-[11px] font-mono font-bold text-slate-400">
          <span>경로 개정: <b className="text-white">v{session.routeRevision}</b></span>
          <span>남은 맞춤시간: <b className="text-emerald-400">{route.personal}분</b></span>
        </div>
      </div>

      <div className="h-[210px] relative shrink-0">
        <KakaoMap
          center={origin}
          level={4}
          markers={[
            { lat: latestSampleRef.current.coordinate.latitude, lng: latestSampleRef.current.coordinate.longitude, title: "나의 위치", type: "you" },
            { lat: destination.lat, lng: destination.lng, title: destination.name, type: "dest" },
          ]}
          routePath={route.mapPoints}
        />

        <div className="absolute bottom-3 left-4 right-4 bg-slate-950/80 backdrop-blur px-3 py-1.5 rounded-lg text-[10.5px] font-mono font-bold text-slate-200 z-10 flex items-center justify-between shadow">
          <span className="flex items-center gap-1.5 truncate">
            <span className={`w-2 h-2 rounded-full ${gpsPulse ? "bg-amber-400 scale-125" : "bg-emerald-400"} transition-all`}></span>
            {gpsIndicator}
          </span>
          <span className="text-blue-400 text-[9.5px]">GPS 5s</span>
        </div>

        <button
          onClick={() => void triggerMockDeviation()}
          disabled={busy}
          className="absolute top-3 right-3 bg-white/90 backdrop-blur p-2 rounded-xl shadow border border-slate-200 text-slate-700 text-[10.5px] font-bold hover:bg-slate-100 disabled:opacity-50 transition-all z-10 flex items-center gap-1 cursor-pointer"
        >
          <Layers className="w-3.5 h-3.5 text-blue-600 animate-pulse" />
          가상 이탈(Reroute)
        </button>
      </div>

      <div className="flex-1 bg-white border-t border-slate-200 shadow flex flex-col overflow-hidden">
        <div className="bg-blue-600 text-white p-4.5 shrink-0 relative">
          <div className="flex justify-between items-start mb-1.5">
            <div>
              <span className="text-[10px] font-black uppercase tracking-widest opacity-80 block">
                전체 {navSteps.length}개 턱 완화 리스트 중 ({navIndex + 1} / {navSteps.length})
              </span>
              <h3 className="text-[17px] font-black tracking-tight mt-0.5">
                {currentStep?.title || "최종 목적지에 거의 도착했습니다."}
              </h3>
            </div>
            {currentStep?.time && (
              <div className="text-right">
                <span className="text-[20px] font-mono font-black leading-none block text-amber-300">{currentStep.time}</span>
                <span className="text-[9.5px] opacity-75">구간 시간</span>
              </div>
            )}
          </div>
          <p className="text-[13px] opacity-90 leading-relaxed">{currentStep?.desc}</p>
          <div className="flex items-center gap-3 border-t border-white/20 mt-3 pt-2">
            <span className="text-[10.5px] font-bold opacity-85 shrink-0">개인 보행 템포 속도 박자</span>
            <PaceBar speedFactor={speedFactor} />
          </div>
        </div>

        {rerouteSuggestion && (
          <div className="bg-amber-50 border-b border-amber-200 px-4 py-3 shrink-0 flex items-start gap-3 animate-fade-in">
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div className="min-w-0 flex-1">
              <h4 className="text-[12.5px] font-black text-amber-800">⚠️ 경로 이탈 감지 (REROUTE_SUGGESTED)</h4>
              <p className="text-[11px] text-amber-700 leading-normal mt-0.5">{rerouteSuggestion.message}</p>
              <div className="flex gap-2.5 mt-2">
                <button
                  onClick={() => void reroute(rerouteSuggestion.reason)}
                  disabled={busy}
                  className="bg-amber-600 hover:bg-amber-700 text-white text-[11px] font-bold py-1 px-3 rounded-md cursor-pointer shadow-sm transition-all disabled:opacity-50"
                >
                  새 경로 재탐색 승인
                </button>
                <button
                  onClick={() => setRerouteSuggestion(null)}
                  className="text-amber-800 text-[11px] font-bold py-1 px-2.5 hover:bg-amber-100 rounded-md cursor-pointer transition-all"
                >
                  이탈 무시
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="bg-slate-50 border-b border-slate-200 px-4 py-2 shrink-0 flex items-center justify-between gap-2 overflow-x-auto custom-scrollbar">
          <span className="text-[10.5px] font-bold text-slate-500 flex items-center gap-1 shrink-0">
            <MapPin className="w-3.5 h-3.5 text-blue-600" />
            지하 GPS 불통 보정역 지정:
          </span>
          <div className="flex gap-1.5 shrink-0 py-0.5">
            {route.stationOptions.length === 0 && <span className="text-[10px] text-slate-400">해당 경로에 지하철역 없음</span>}
            {route.stationOptions.map((station) => (
              <button
                key={station.id}
                onClick={() => void handleStationSnap(station)}
                disabled={busy}
                className={`text-[10px] font-bold px-2 py-0.8 rounded-md border transition-all cursor-pointer disabled:opacity-50 ${
                  currentStation?.id === station.id
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-white text-slate-600 border-slate-200 hover:border-blue-500"
                }`}
              >
                {station.name}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-3.5 custom-scrollbar bg-slate-50">
          <div className="space-y-1.5">
            {navSteps.map((step, idx) => {
              const isCompleted = idx < navIndex;
              const isActive = idx === navIndex;
              return (
                <div
                  key={step.legId || idx}
                  className={`flex items-center gap-3 p-3 rounded-xl border transition-all ${
                    isActive ? "bg-white border-blue-600 shadow-sm" : "bg-slate-100/60 border-slate-200"
                  } ${isCompleted ? "opacity-45" : ""}`}
                >
                  <span className={`w-5.5 h-5.5 rounded-full flex items-center justify-center font-mono text-[10px] font-black shrink-0 ${
                    isCompleted ? "bg-blue-600 text-white" : "bg-slate-200 text-slate-500"
                  }`}>
                    {isCompleted ? "✓" : idx + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <h4 className="text-[12.5px] font-bold text-slate-900">{step.title}</h4>
                    <p className="text-[11px] text-slate-500 truncate">{step.desc}</p>
                  </div>
                  {step.facilityStatus === "UNKNOWN" && (
                    <span className="bg-amber-100 text-amber-700 font-bold px-1.5 py-0.5 rounded text-[9px] uppercase shrink-0">UNKNOWN</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="p-3.5 bg-slate-100 border-t border-slate-200 shrink-0 flex gap-2.5">
          {(currentStep?.mode === "bus" || currentStep?.mode === "subway") && (
            <button
              onClick={() => void handleMissedTransit()}
              disabled={busy}
              className="py-2.5 px-3.5 bg-red-50 hover:bg-red-100 text-red-600 font-bold rounded-xl text-[12.5px] transition-all border border-red-100 cursor-pointer disabled:opacity-50"
            >
              차량을 놓쳤어요
            </button>
          )}
          <button
            onClick={() => void handleNextStep()}
            disabled={busy}
            className="flex-1 py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl text-[13.5px] flex items-center justify-center gap-1.5 shadow-sm transform active:scale-95 transition-all cursor-pointer disabled:opacity-50"
          >
            <span>{navIndex + 1 === navSteps.length ? "목적지 하차 완료" : "다음 위험턱 확인"}</span>
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
