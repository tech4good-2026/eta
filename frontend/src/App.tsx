/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Search,
  RefreshCw,
  User,
  ShieldCheck,
  MapPin,
  Bus,
  Train,
  ArrowUpDown,
  Navigation,
  Info,
  ChevronRight,
  AlertTriangle,
  Locate,
  MapPinned,
  Settings,
  WifiOff,
  Wifi,
  Phone,
  Link2
} from "lucide-react";
import type { ApiNavigationCompletion, ApiNavigationSession } from "./api/types";
import { api } from "./api/client";
import {
  mapModeToApi,
  mapPlaceToApi,
  mapProfileFromApi,
  mapProfileToApi,
  mapRouteSearchFromApi,
} from "./api/mappers";
import { searchKakaoPlaces } from "./services/kakaoPlaces";
import { Place, RouteInfo, UserProfile } from "./types";
import { PaceBar } from "./components/PaceBar";
import { KakaoMap } from "./components/KakaoMap";
import { AuthScreen } from "./components/AuthScreen";
import { ProfileScreen } from "./components/ProfileScreen";
import { NavigationScreen } from "./components/NavigationScreen";
import { ArrivalScreen } from "./components/ArrivalScreen";
import { clearDemoSession, getDemoSession } from "./utils/demoSession";
import { getSpeedMultiplier } from "./utils/routing";

export default function App() {
  // Navigation Screens: login | main | profile-setup | profile-edit | search | place | route-search | route-detail | navigation | arrival
  const [screen, setScreen] = useState<string>("login");

  // Auth state
  const [userEmail, setUserEmail] = useState<string>("");
  const [profile, setProfile] = useState<UserProfile>({
    chars: [],
    devices: [],
    avoidStairs: false,
    elevatorRequired: false,
    lowFloorBusRequired: false,
    avoidSteepSlopes: false,
    walkingSpeedMps: 1.0,
    walkingSpeedSource: "CALCULATED",
    walkingSpeedSampleCount: 0,
  });

  // UI status modifiers
  const [isOffline, setIsOffline] = useState<boolean>(false);
  const [hasNetworkError, setHasNetworkError] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [geolocationStatus, setGeolocationStatus] = useState<"PROMPT" | "GRANTED" | "DENIED">("PROMPT");
  const [currentCoords, setCurrentCoords] = useState<{ lat: number; lng: number }>({ lat: 37.5547, lng: 126.9707 }); // 서울역

  // Search/Routing state
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [searchTarget, setSearchTarget] = useState<Place | null>(null);
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [mode, setMode] = useState<"transit" | "taxi" | "walk">("transit");
  const [routes, setRoutes] = useState<RouteInfo[]>([]);
  const [selectedRoute, setSelectedRoute] = useState<RouteInfo | null>(null);
  const [routeSearchStatus, setRouteSearchStatus] = useState<"SUCCESS" | "NO_ACCESSIBLE_ROUTE">("SUCCESS");
  const [placeResults, setPlaceResults] = useState<Place[]>([]);
  const [recentPlaces, setRecentPlaces] = useState<Place[]>([]);
  const [isPlaceSearching, setIsPlaceSearching] = useState(false);
  const [placeSearchError, setPlaceSearchError] = useState(false);
  const [navigationSession, setNavigationSession] = useState<ApiNavigationSession | null>(null);
  const [navigationCompletion, setNavigationCompletion] = useState<ApiNavigationCompletion | null>(null);
  const [navigationStartSpeed, setNavigationStartSpeed] = useState(1);
  const routeCacheRef = useRef(new Map<string, { status: "SUCCESS" | "NO_ACCESSIBLE_ROUTE"; routes: RouteInfo[] }>());

  // Toast status
  const [toastMessage, setToastMessage] = useState<string>("");
  const [toastVisible, setToastVisible] = useState<boolean>(false);

  // Restore only the demo token, then fetch the mutable server profile.
  useEffect(() => {
    const session = getDemoSession();
    if (!session) return;
    void api.getProfile()
      .then((serverProfile) => {
        setUserEmail(session.email);
        setProfile(mapProfileFromApi(serverProfile));
        setScreen("main");
      })
      .catch(() => {
        clearDemoSession();
        setHasNetworkError(true);
      });
  }, []);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setToastVisible(true);
  };

  useEffect(() => {
    if (toastVisible) {
      const timer = setTimeout(() => setToastVisible(false), 2400);
      return () => clearTimeout(timer);
    }
  }, [toastVisible]);

  // Request browser location permission (F-MAP-02)
  const handleRequestLocation = () => {
    if (!navigator.geolocation) {
      setGeolocationStatus("DENIED");
      showToast("브라우저가 현재 위치 탐색을 제공하지 않습니다.");
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGeolocationStatus("GRANTED");
        const nextCoords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        setCurrentCoords(nextCoords);
        showToast("위치 권한 동의 완료: 현위치 주변 안전 노선을 스캔합니다.");

        // Setup current position as custom starting place
        const customOrigin: Place = {
          id: "current-gps",
          name: "나의 현위치 (GPS)",
          addr: "GPS로 수신한 현재 실시간 좌표",
          tag: "현재 수신지점",
          lat: nextCoords.lat,
          lng: nextCoords.lng,
          category: "현위치",
          phone: "없음",
          placeUrl: ""
        };
        setOrigin(customOrigin);
      },
      () => {
        setGeolocationStatus("DENIED");
        showToast("위치 권한이 거부되었습니다. 직접 검색 모드를 이용해 주세요.");
      }
    );
  };

  const handleAuthSuccess = async (email: string) => {
    const serverProfile = await api.getProfile();
    setUserEmail(email);
    setProfile(mapProfileFromApi(serverProfile));
    setScreen("main");
  };

  const handleProfileComplete = async (updatedProfile: UserProfile) => {
    const saved = await api.updateProfile(mapProfileToApi(updatedProfile));
    setProfile(mapProfileFromApi(saved));
    routeCacheRef.current.clear();
    setScreen("main");
  };

  // Kakao Places keyword search: minimum 2 chars with a 300ms debounce.
  useEffect(() => {
    const query = searchQuery.trim();
    if (screen !== "search" || query.length < 2) {
      setPlaceResults([]);
      setIsPlaceSearching(false);
      setPlaceSearchError(false);
      return;
    }

    let active = true;
    const timer = window.setTimeout(() => {
      setIsPlaceSearching(true);
      setPlaceSearchError(false);
      void searchKakaoPlaces(query)
        .then((results) => {
          if (!active) return;
          setPlaceResults(results);
          setRecentPlaces(results.slice(0, 6));
        })
        .catch(() => {
          if (!active) return;
          setPlaceResults([]);
          setPlaceSearchError(true);
        })
        .finally(() => {
          if (active) setIsPlaceSearching(false);
        });
    }, 300);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [screen, searchQuery]);

  const openPlace = (p: Place) => {
    setSearchTarget(p);
    setRecentPlaces((current) => [p, ...current.filter((place) => place.id !== p.id)].slice(0, 6));
    setScreen("place");
  };

  const handleSetPlace = (type: "origin" | "destination") => {
    if (!searchTarget) return;

    if (type === "origin") {
      setOrigin(searchTarget);
    } else {
      setDestination(searchTarget);
    }

    const nextOrigin = type === "origin" ? searchTarget : origin;
    const nextDest = type === "destination" ? searchTarget : destination;

    if (nextOrigin && nextDest) {
      handleQueryRoutes(mode, nextOrigin, nextDest);
    } else {
      showToast(`${type === "origin" ? "출발지" : "목적지"} 설정이 완료되었습니다. 남은 한 곳을 등록하세요.`);
      setScreen("main");
    }
  };

  const swapOD = () => {
    const temp = origin;
    setOrigin(destination);
    setDestination(temp);
    if (destination && origin) {
      handleQueryRoutes(mode, destination, origin);
    }
  };

  // Dynamic Route Fetching with Simulated Skeleton Loaders (F-ROUTE-01 / Section 6)
  const handleQueryRoutes = async (nextMode: "transit" | "taxi" | "walk", src = origin, dest = destination) => {
    if (!src || !dest) return;
    setMode(nextMode);

    if (isOffline) {
      showToast("오프라인 상태입니다. 경로 재탐색이 제한됩니다.");
      return;
    }

    setIsLoading(true);
    setHasNetworkError(false);

    try {
      const cacheKey = `${src.id}:${dest.id}:${nextMode}`;
      const cached = routeCacheRef.current.get(cacheKey);
      if (cached) {
        setRoutes(cached.routes);
        setRouteSearchStatus(cached.status);
        setSelectedRoute(null);
        setScreen("route-search");
        return;
      }

      const response = await api.searchRoutes({
        origin: mapPlaceToApi(src),
        destination: mapPlaceToApi(dest),
        mode: mapModeToApi(nextMode),
        departureAt: new Date().toISOString(),
      });
      const result = mapRouteSearchFromApi(response);
      routeCacheRef.current.set(cacheKey, { status: result.status, routes: result.routes });
      setRoutes(result.routes);
      setRouteSearchStatus(result.status);
      setSelectedRoute(null);
      setScreen("route-search");
    } catch (e) {
      setHasNetworkError(true);
    } finally {
      setIsLoading(false);
    }
  };

  // Offline status banner helper
  const handleToggleOffline = () => {
    const nextOffline = !isOffline;
    setIsOffline(nextOffline);
    if (nextOffline) {
      showToast("오프라인 연결 상태로 전환되었습니다. (실시간 검색 통제)");
    } else {
      showToast("온라인 네트워크 복구 완료!");
    }
  };

  // Speed factor helper text (mps to human readable style)
  const speedRatio = getSpeedMultiplier(profile);

  const handleStartNavigation = async () => {
    if (!selectedRoute) return;
    setIsLoading(true);
    try {
      const session = await api.startNavigation(selectedRoute.id);
      setNavigationSession(session);
      setNavigationCompletion(null);
      setNavigationStartSpeed(profile.walkingSpeedMps);
      setScreen("navigation");
    } catch {
      setHasNetworkError(true);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCompleteNavigation = async (sessionId: string) => {
    const completion = await api.completeNavigation(sessionId);
    setNavigationCompletion(completion);
    setProfile((current) => ({
      ...current,
      walkingSpeedMps: completion.walkingSpeed.walkingSpeedMps,
      walkingSpeedSource: completion.walkingSpeed.walkingSpeedSource === "LEARNED" ? "LEARNED" : "CALCULATED",
      walkingSpeedSampleCount: completion.walkingSpeed.walkingSpeedSampleCount,
    }));
    setScreen("arrival");
  };

  return (
    <div className="flex justify-center items-center min-h-screen bg-slate-900 font-sans p-0 sm:p-4">
      {/* Smartphone frame container layout */}
      <div className="w-full max-w-[428px] h-screen sm:h-[860px] bg-slate-50 shadow-2xl relative flex flex-col overflow-hidden sm:rounded-[40px] sm:border-[8px] sm:border-slate-850">

        {/* Offline Banner indicator (Section 6 & 11) */}
        {isOffline && (
          <div className="bg-red-500 text-white text-[11px] font-black px-4 py-2 flex items-center justify-between z-50 shrink-0">
            <span className="flex items-center gap-1.5 animate-pulse">
              <WifiOff className="w-3.5 h-3.5" />
              오프라인 모드 활성화됨. 새로운 검색 및 경로 재탐색이 중단됩니다.
            </span>
            <button
              onClick={handleToggleOffline}
              className="bg-white/20 hover:bg-white/30 px-2 py-0.5 rounded text-[10px] uppercase font-bold"
            >
              연결
            </button>
          </div>
        )}

        {/* Global Network Fail Simulation bar */}
        {hasNetworkError && (
          <div className="bg-amber-600 text-white text-[11px] font-black px-4 py-2 flex items-center justify-between z-50 shrink-0">
            <span className="flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              현재 경로 정보를 불러오지 못했습니다.
            </span>
            <button
              onClick={() => {
                setHasNetworkError(false);
                if (origin && destination) handleQueryRoutes(mode, origin, destination);
              }}
              className="bg-white text-amber-700 font-black px-2.5 py-0.5 rounded-md text-[10px]"
            >
              재시도
            </button>
          </div>
        )}

        {/* SCREEN: AUTH */}
        {screen === "login" && (
          <AuthScreen onAuthSuccess={handleAuthSuccess} showToast={showToast} />
        )}

        {/* SCREEN: INITIAL PROFILE SETUP */}
        {screen === "profile-setup" && (
          <ProfileScreen
            email={userEmail}
            initialProfile={profile}
            onComplete={handleProfileComplete}
            showToast={showToast}
          />
        )}

        {/* SCREEN: MAIN MAP VIEW */}
        {screen === "main" && (
          <div className="flex-1 flex flex-col" id="view-main-screen">
            {/* Header Profiling Bar */}
            <div className="bg-white border-b border-slate-200 px-5 py-4 shrink-0 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center">
                  <User className="w-5 h-5 text-slate-700" />
                </div>
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[14px] font-black text-slate-800 truncate max-w-[130px]">
                      {userEmail.split("@")[0]} 님
                    </span>
                    <span className="bg-blue-50 text-blue-600 font-extrabold px-1.5 py-0.2 rounded text-[9.5px]">
                      {profile.walkingSpeedSource === "LEARNED" ? "학습형속도" : "기준속도"}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] text-slate-500 font-bold mt-0.5">
                    <span>보행속도: {profile.walkingSpeedMps}m/s</span>
                    <span>({Math.round(speedRatio * 100)}%)</span>
                  </div>
                </div>
              </div>

              <div className="flex gap-1.5">
                {/* Offline trigger toggle for verification */}
                <button
                  onClick={handleToggleOffline}
                  className={`w-8 h-8 rounded-full flex items-center justify-center border transition-all ${
                    isOffline
                      ? "bg-red-50 text-red-500 border-red-200"
                      : "bg-slate-50 text-slate-500 border-slate-200 hover:bg-slate-100"
                  }`}
                  title="인터넷 연결 상태 토글"
                >
                  {isOffline ? <WifiOff className="w-4 h-4" /> : <Wifi className="w-4 h-4" />}
                </button>
                <button
                  onClick={() => setScreen("profile-edit")}
                  className="w-8 h-8 rounded-full bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-600 hover:bg-slate-100 transition-all cursor-pointer"
                  title="신체 프로필 수정"
                >
                  <Settings className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Map container */}
            <div className="flex-1 relative">
              <KakaoMap
                center={origin || currentCoords}
                level={4}
                markers={
                  origin
                    ? [{ lat: origin.lat, lng: origin.lng, title: origin.name, type: "origin" }]
                    : []
                }
              />

              {/* Float Search Entry Panel */}
              <div className="absolute top-4 left-4 right-4 z-10 space-y-2">
                <div
                  onClick={() => {
                    if (isOffline) {
                      showToast("오프라인 상태입니다. 새로운 탐색이 불가능합니다.");
                      return;
                    }
                    setScreen("search");
                  }}
                  className="bg-white p-3.5 rounded-[18px] border border-slate-200 shadow-md flex items-center gap-3 cursor-pointer hover:bg-slate-50 transition-all"
                >
                  <Search className="w-5 h-5 text-slate-400" />
                  <span className="text-[13.5px] font-bold text-slate-400">
                    {destination ? destination.name : "어디로 안전하게 우회하여 이동할까요?"}
                  </span>
                </div>

                {origin && (
                  <div className="bg-white/95 backdrop-blur px-3 py-2 rounded-xl border border-slate-200 shadow-sm flex justify-between items-center text-[11.5px] font-bold text-slate-700">
                    <span className="flex items-center gap-1.5 truncate">
                      <MapPin className="w-3.5 h-3.5 text-blue-600 shrink-0" />
                      출발: {origin.name}
                    </span>
                    <button
                      onClick={() => { setOrigin(null); showToast("출발지 설정을 해제했습니다."); }}
                      className="text-red-500 hover:text-red-600 pl-2 cursor-pointer"
                    >
                      취소
                    </button>
                  </div>
                )}
              </div>

              {/* Current Location Request Guide Box (F-MAP-01 / F-MAP-02) */}
              <div className="absolute bottom-4 left-4 right-4 z-10 flex flex-col gap-2">
                {geolocationStatus !== "GRANTED" && (
                  <div className="bg-white/95 backdrop-blur p-3.5 rounded-[20px] border border-slate-200 shadow-md">
                    <h4 className="text-[12.5px] font-black text-slate-800 flex items-center gap-1.5">
                      <Locate className="w-4.5 h-4.5 text-blue-600 animate-pulse" />
                      안전한 ETA 이동을 위해 현위치를 켤까요?
                    </h4>
                    <p className="text-[11px] text-slate-500 leading-normal mt-0.5">
                      위치 권한 거부 시 현재 위치 좌표가 제한되며, 출발지와 목적지를 리스트에서 수동 지정해 안전 우회로를 찾을 수 있습니다.
                    </p>
                    <div className="flex gap-2 mt-2.5">
                      <button
                        onClick={handleRequestLocation}
                        className="bg-blue-600 hover:bg-blue-700 text-white font-bold text-[11px] py-1.5 px-3 rounded-lg cursor-pointer transition-all"
                      >
                        내 위치 자동 동의
                      </button>
                      <button
                        onClick={() => { setGeolocationStatus("DENIED"); showToast("수동 검색 탐색 모드로 고정합니다."); }}
                        className="bg-slate-100 text-slate-700 font-bold text-[11px] py-1.5 px-3 rounded-lg cursor-pointer hover:bg-slate-200 transition-all"
                      >
                        동의 안 함 (수동 입력)
                      </button>
                    </div>
                  </div>
                )}

                {/* Reset button to default test map center */}
                {geolocationStatus === "GRANTED" && (
                  <button
                    onClick={() => setCurrentCoords({ lat: 37.5547, lng: 126.9707 })}
                    className="w-10 h-10 rounded-full bg-white border border-slate-200 shadow flex items-center justify-center text-slate-600 self-end hover:bg-slate-50 transition-all cursor-pointer"
                    title="현위치로"
                  >
                    <Locate className="w-4.5 h-4.5 text-blue-600" />
                  </button>
                )}
              </div>
            </div>

            {/* Recents list and POIs area */}
            <div className="bg-white border-t border-slate-200 rounded-t-[28px] p-5 shrink-0 shadow">
              <h3 className="text-[13.5px] font-black text-slate-900 mb-2.5 flex items-center gap-1.5">
                <MapPinned className="w-4.5 h-4.5 text-blue-600" />
                최근 카카오 장소 검색 결과
              </h3>
              <div className="space-y-2 max-h-[145px] overflow-y-auto custom-scrollbar">
                {recentPlaces.length === 0 && (
                  <div className="p-3 rounded-xl border border-dashed border-slate-200 text-center text-[11px] text-slate-400">
                    목적지를 검색하면 최근 결과가 여기에 표시됩니다.
                  </div>
                )}
                {recentPlaces.map((p) => (
                  <div
                    key={p.id}
                    onClick={() => openPlace(p)}
                    className="p-3 rounded-xl hover:bg-slate-50 border border-slate-100 transition-all flex justify-between items-center cursor-pointer"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[13px] font-bold text-slate-800 truncate">{p.name}</span>
                        <span className="bg-emerald-50 text-emerald-600 text-[9.5px] font-extrabold px-1.5 py-0.2 rounded-md">
                          {p.category}
                        </span>
                      </div>
                      <span className="text-[11px] text-slate-500 truncate block mt-0.5">{p.addr}</span>
                    </div>
                    <ChevronRight className="w-4.5 h-4.5 text-slate-400 shrink-0 ml-2" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* SCREEN: SEARCH VIEW (F-PLACE-01) */}
        {screen === "search" && (
          <div className="flex-1 flex flex-col bg-white" id="view-search-screen">
            {/* Search Top Header */}
            <div className="p-4.5 border-b border-slate-200 shrink-0 flex items-center gap-3">
              <button
                onClick={() => setScreen("main")}
                className="w-8 h-8 rounded-full bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-700 cursor-pointer"
              >
                <ArrowLeft className="w-4 h-4" />
              </button>
              <div className="flex-1 relative">
                <input
                  type="text"
                  autoFocus
                  placeholder="2자 이상의 장소명 또는 주소를 검색하세요..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full text-[13.5px] pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-blue-500 text-slate-950 font-bold"
                />
                <Search className="w-4.5 h-4.5 text-slate-400 absolute left-3.5 top-3.2" />
              </div>
            </div>

            {/* Results */}
            <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
              {searchQuery.trim().length < 2 ? (
                <div className="text-center py-12 text-slate-400 space-y-1">
                  <p className="text-[13px] font-bold">검색어를 입력해 주세요.</p>
                  <p className="text-[11px]">검색 효율 향상을 위해 최소 2자 이상 입력이 필수로 통제됩니다.</p>
                </div>
              ) : isPlaceSearching ? (
                <div className="text-center py-12 text-slate-400 space-y-1.5">
                  <RefreshCw className="w-5 h-5 animate-spin mx-auto text-blue-500" />
                  <p className="text-[12px] font-bold">카카오 장소를 검색하고 있습니다.</p>
                </div>
              ) : placeSearchError ? (
                <div className="text-center py-12 text-amber-600 space-y-1.5">
                  <p className="text-[13px] font-black">장소 검색 정보를 불러오지 못했습니다.</p>
                  <p className="text-[11.5px]">카카오 JavaScript 키와 네트워크 상태를 확인해 주세요.</p>
                </div>
              ) : placeResults.length === 0 ? (
                <div className="text-center py-12 text-slate-400 space-y-1.5">
                  <p className="text-[13px] font-black text-slate-600">검색 결과가 없습니다.</p>
                  <p className="text-[11.5px] leading-relaxed">다른 장소명이나 주소를 입력해 주세요. (Section 6)</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {placeResults.map((p) => (
                    <div
                      key={p.id}
                      onClick={() => openPlace(p)}
                      className="p-3.5 rounded-xl border border-slate-150 hover:bg-slate-50 transition-all cursor-pointer flex justify-between items-start"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-[13.5px] font-black text-slate-800 truncate">{p.name}</span>
                          <span className="bg-slate-100 text-slate-600 font-bold text-[9.5px] px-1.5 py-0.2 rounded">
                            {p.category}
                          </span>
                        </div>
                        <p className="text-[11.5px] text-slate-500 truncate mt-0.5">{p.addr}</p>
                        {p.phone && p.phone !== "없음" && (
                          <span className="text-[10px] text-slate-400 font-mono mt-1 block">전화: {p.phone}</span>
                        )}
                      </div>
                      <ChevronRight className="w-4 h-4 text-slate-400 mt-1 shrink-0 ml-2" />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* SCREEN: PLACE DETAIL (F-PLACE-02) */}
        {screen === "place" && searchTarget && (
          <div className="flex-1 flex flex-col" id="view-place-screen">
            <div className="bg-white border-b border-slate-200 px-5 py-4 shrink-0 flex items-center gap-3">
              <button
                onClick={() => setScreen(searchQuery.trim().length >= 2 ? "search" : "main")}
                className="w-8 h-8 rounded-full bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-700 cursor-pointer"
              >
                <ArrowLeft className="w-4 h-4" />
              </button>
              <h2 className="text-[15px] font-black text-slate-800">장소 상세 분석</h2>
            </div>

            <div className="flex-1 relative">
              <KakaoMap
                center={searchTarget}
                level={3}
                markers={[{ lat: searchTarget.lat, lng: searchTarget.lng, title: searchTarget.name, type: "dest" }]}
              />

              {/* Overlay Place Information Card */}
              <div className="absolute bottom-4 left-4 right-4 bg-white/95 backdrop-blur p-4.5 rounded-[22px] border border-slate-200 shadow-lg space-y-3 z-10">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-[16.5px] font-black text-slate-900 leading-none">{searchTarget.name}</h3>
                    <span className="bg-blue-50 text-blue-600 font-extrabold text-[10px] px-2 py-0.5 rounded-md">
                      {searchTarget.category}
                    </span>
                  </div>
                  <p className="text-[12px] text-slate-500 mt-1 leading-normal">{searchTarget.addr}</p>
                </div>

                <div className="border-t border-slate-100 my-1"></div>

                <div className="flex justify-between items-center text-[11px] text-slate-500 font-bold">
                  {searchTarget.phone && searchTarget.phone !== "없음" ? (
                    <span className="flex items-center gap-1.5">
                      <Phone className="w-3.5 h-3.5 text-blue-500 shrink-0" />
                      전화: {searchTarget.phone}
                    </span>
                  ) : (
                    <span>전화번호 정보 없음</span>
                  )}

                  {searchTarget.placeUrl && (
                    <a
                      href={searchTarget.placeUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:underline flex items-center gap-1"
                    >
                      <Link2 className="w-3.5 h-3.5" />
                      장소 홈페이지
                    </a>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-2 pt-1">
                  <button
                    onClick={() => handleSetPlace("origin")}
                    className="py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 font-extrabold text-[12.5px] rounded-xl cursor-pointer transition-all flex items-center justify-center gap-1"
                  >
                    출발지로 지정
                  </button>
                  <button
                    onClick={() => handleSetPlace("destination")}
                    className="py-3 bg-blue-600 hover:bg-blue-700 text-white font-extrabold text-[12.5px] rounded-xl cursor-pointer shadow-sm transition-all flex items-center justify-center gap-1"
                  >
                    목적지로 지정
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* SCREEN: ROUTE COMPARE SEARCH (F-ROUTE-01 / 02 / 03 / 04 / 06) */}
        {screen === "route-search" && origin && destination && (
          <div className="flex-1 flex flex-col" id="view-route-search-screen">
            {/* Header comparison controls */}
            <div className="bg-white border-b border-slate-200 p-4 shrink-0 shadow-sm space-y-3">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setScreen("main")}
                  className="w-8 h-8 rounded-full bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-700 cursor-pointer"
                >
                  <ArrowLeft className="w-4 h-4" />
                </button>
                <div className="flex-1 flex items-center gap-2 text-[13px] font-bold text-slate-800 truncate">
                  <span className="truncate max-w-[130px]">{origin.name}</span>
                  <ArrowUpDown className="w-3.5 h-3.5 text-slate-400 rotate-90 shrink-0" onClick={swapOD} />
                  <span className="truncate max-w-[130px]">{destination.name}</span>
                </div>
              </div>

              {/* Mode switching tabs */}
              <div className="flex bg-slate-100 p-1 rounded-xl">
                {(["transit", "taxi", "walk"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => handleQueryRoutes(m)}
                    className={`flex-1 py-2 rounded-lg font-black text-[12px] uppercase transition-all cursor-pointer ${
                      mode === m
                        ? "bg-white text-blue-600 shadow-sm"
                        : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    {m === "transit" ? "대중교통" : m === "taxi" ? "택시 연계" : "안전도보"}
                  </button>
                ))}
              </div>
            </div>

            {/* Content list or Skeleton state */}
            <div className="flex-1 overflow-y-auto px-4 py-3 custom-scrollbar">
              {isLoading ? (
                /* Beautiful accessible Loading skeleton list (Section 6) */
                <div className="space-y-3 py-2">
                  <div className="p-3 bg-white border border-slate-200 rounded-2xl animate-pulse space-y-2.5">
                    <div className="h-4.5 bg-slate-200 rounded-md w-3/4"></div>
                    <div className="h-4 bg-slate-200 rounded-md w-1/2"></div>
                    <div className="flex gap-2 pt-1">
                      <div className="h-5 bg-slate-200 rounded-full w-16"></div>
                      <div className="h-5 bg-slate-200 rounded-full w-20"></div>
                    </div>
                  </div>
                  <div className="p-3 bg-white border border-slate-200 rounded-2xl animate-pulse space-y-2.5">
                    <div className="h-4.5 bg-slate-200 rounded-md w-2/3"></div>
                    <div className="h-4 bg-slate-200 rounded-md w-1/3"></div>
                  </div>
                  <button
                    onClick={() => setIsLoading(false)}
                    className="w-full py-2 bg-slate-200 hover:bg-slate-300 text-slate-600 rounded-xl text-[11px] font-bold cursor-pointer"
                  >
                    불러오기 중단 및 취소
                  </button>
                </div>
              ) : (
                <div className="space-y-3 py-1">

                  {/* F-ROUTE-06: Alternative Suggestion Card if all Transit options are UNAVAILABLE */}
                  {mode === "transit" && routeSearchStatus === "NO_ACCESSIBLE_ROUTE" && (
                    <div className="bg-amber-50 border border-amber-200 p-4 rounded-2xl space-y-2.5">
                      <div className="flex items-start gap-2 text-amber-800">
                        <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5 text-amber-600" />
                        <div>
                          <h4 className="text-[13px] font-black">접근 가능한 대중교통 경로 없음</h4>
                          <p className="text-[11px] leading-normal text-amber-700 mt-0.5">
                            현재 설정된 <b>신체 프로필</b> 및 <b>안전 옵션</b>(계단 회피, 엘리베이터 필수 등)을 완전히 충족하는 대중교통 경로 수립이 불가능합니다. (status=NO_ACCESSIBLE_ROUTE)
                          </p>
                        </div>
                      </div>
                      <button
                        onClick={() => handleQueryRoutes("taxi")}
                        className="w-full py-2 bg-amber-600 hover:bg-amber-700 text-white font-bold rounded-xl text-[11.5px] cursor-pointer"
                      >
                        대체 보완수단인 장애인 콜택시 탭으로 강제 이동
                      </button>
                    </div>
                  )}

                  {/* Routes Cards list */}
                  {routes.map((route, rIdx) => {
                    const isAccessible = route.accessibilityStatus === "ACCESSIBLE";
                    const isCaution = route.accessibilityStatus === "CAUTION";
                    const isUnavailable = route.accessibilityStatus === "UNAVAILABLE";

                    return (
                      <div
                        key={route.id}
                        onClick={() => {
                          setSelectedRoute(route);
                          setScreen("route-detail");
                        }}
                        className={`p-4 bg-white rounded-2xl border-[1.5px] hover:border-blue-500 transition-all cursor-pointer shadow-sm space-y-3 ${
                          isUnavailable ? "opacity-60 bg-slate-50 border-slate-200" : "border-slate-150"
                        }`}
                      >
                        <div className="flex justify-between items-start gap-2">
                          <div className="space-y-1 min-w-0">
                            <span className="text-[10px] font-black uppercase tracking-wider text-slate-400 block">
                              옵션 {rIdx + 1}
                            </span>
                            <h4 className="text-[13.5px] font-bold text-slate-800 truncate leading-tight">
                              {route.label}
                            </h4>
                          </div>

                          {/* Dynamic Accessibility tags */}
                          <span className={`text-[10px] font-black px-2 py-0.6 rounded shrink-0 ${
                            isAccessible
                              ? "bg-emerald-50 text-emerald-600"
                              : isCaution
                                ? "bg-amber-50 text-amber-600"
                                : "bg-red-50 text-red-500"
                          }`}>
                            {isAccessible ? "접근 용이" : isCaution ? "확인요망" : "불가 경고"}
                          </span>
                        </div>

                        {/* Side-by-side Personalized Time / General Time Display (F-ROUTE-04) */}
                        <div className="flex justify-between items-end bg-slate-50 p-2.5 rounded-xl border border-slate-100">
                          <div>
                            <span className="text-[9px] text-slate-400 font-extrabold block uppercase">일반 소요</span>
                            <span className="text-[13.5px] font-mono font-bold text-slate-500">{route.general}분</span>
                          </div>
                          <div className="text-right">
                            <span className="text-[9px] text-blue-500 font-extrabold block uppercase">개인화 템포 소요</span>
                            <span className="text-[18px] font-mono font-black text-blue-600 leading-none">{route.personal}분</span>
                          </div>
                        </div>

                        {/* Path meta: Fare, transfers, walk distance */}
                        <div className="flex justify-between items-center text-[11px] font-bold text-slate-500">
                          <span className="flex items-center gap-1.5">
                            {route.mode === "transit" && <Train className="w-3.5 h-3.5 text-slate-400" />}
                            환승 {route.transfers}회 • 보행거리 {route.walk}m
                          </span>
                          <span className="text-slate-800">
                            {route.fare > 0 ? `${route.fare.toLocaleString()}원` : "무료 연계"}
                          </span>
                        </div>

                        {/* Critical warnings notice block */}
                        {route.notices.length > 0 && (
                          <div className="space-y-1.5 pt-1 border-t border-slate-100">
                            {route.notices.map((n, idx) => (
                              <div
                                key={idx}
                                className={`flex items-start gap-1.5 text-[10.5px] leading-relaxed ${
                                  n.warn ? "text-red-500 font-extrabold" : "text-slate-500 font-medium"
                                }`}
                              >
                                {n.warn ? (
                                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-red-500 animate-pulse" />
                                ) : (
                                  <Info className="w-3.5 h-3.5 shrink-0 mt-0.5 text-slate-400" />
                                )}
                                <span>{n.text}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* SCREEN: ROUTE LEG DETAILS (F-ROUTE-05) */}
        {screen === "route-detail" && selectedRoute && origin && destination && (
          <div className="flex-1 flex flex-col" id="view-route-detail-screen">
            <div className="bg-white border-b border-slate-200 px-5 py-4 shrink-0 flex items-center justify-between shadow-sm">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setScreen("route-search")}
                  className="w-8 h-8 rounded-full bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-700 cursor-pointer"
                >
                  <ArrowLeft className="w-4 h-4" />
                </button>
                <h2 className="text-[14.5px] font-black text-slate-800">우회 경로 입체 상세</h2>
              </div>
              <span className={`text-[10px] font-black px-2 py-0.6 rounded ${
                selectedRoute.accessibilityStatus === "ACCESSIBLE"
                  ? "bg-emerald-50 text-emerald-600"
                  : selectedRoute.accessibilityStatus === "CAUTION"
                    ? "bg-amber-50 text-amber-600"
                    : "bg-red-50 text-red-500"
              }`}>
                {selectedRoute.accessibilityStatus === "ACCESSIBLE" ? "보도 검증됨" : "확인 필요"}
              </span>
            </div>

            <div className="h-[180px] shrink-0">
              <KakaoMap
                center={origin}
                level={4}
                markers={[
                  { lat: origin.lat, lng: origin.lng, title: origin.name, type: "origin" },
                  { lat: destination.lat, lng: destination.lng, title: destination.name, type: "dest" }
                ]}
                routePath={selectedRoute.mapPoints}
              />
            </div>

            {/* List of segment blocks containing facility details */}
            <div className="flex-1 overflow-y-auto px-5 py-4 bg-white custom-scrollbar">
              <div className="space-y-4 relative before:absolute before:left-3 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-100">
                {selectedRoute.segments.map((seg, idx) => {
                  return (
                    <div key={idx} className="flex gap-4 relative">
                      <span className={`w-6.5 h-6.5 rounded-full flex items-center justify-center shrink-0 border-[1.5px] z-10 ${
                        seg.mode === "walk"
                          ? "bg-blue-50 border-blue-500 text-blue-500"
                          : seg.mode === "bus"
                            ? "bg-orange-50 border-orange-500 text-orange-500"
                            : seg.mode === "subway"
                              ? "bg-teal-50 border-teal-500 text-teal-500"
                              : "bg-purple-50 border-purple-500 text-purple-500"
                      }`}>
                        {seg.mode === "walk" ? (
                          <Navigation className="w-3.5 h-3.5 rotate-45" />
                        ) : seg.mode === "bus" ? (
                          <Bus className="w-3.5 h-3.5" />
                        ) : (
                          <Train className="w-3.5 h-3.5" />
                        )}
                      </span>

                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex justify-between items-start gap-2">
                          <h4 className="text-[13px] font-black text-slate-800 leading-tight">
                            {seg.title}
                          </h4>
                          <span className="text-[12px] font-mono font-bold text-slate-500 shrink-0">
                            {seg.time}
                          </span>
                        </div>

                        <p className="text-[11.5px] text-slate-500 leading-relaxed">
                          {seg.desc}
                        </p>

                        <div className="flex flex-wrap gap-1 pt-1">
                          {seg.tags?.map((t, tIdx) => (
                            <span key={tIdx} className="bg-slate-50 border border-slate-150 text-slate-600 text-[9.5px] font-bold px-1.5 py-0.2 rounded-md">
                              {t}
                            </span>
                          ))}

                          {/* Render facility UNKNOWN warning badge explicitly (F-ROUTE-05 / Section 6) */}
                          {seg.facilityStatus === "UNKNOWN" && (
                            <span className="bg-amber-100 border border-amber-200 text-amber-700 font-extrabold text-[9.5px] px-1.5 py-0.2 rounded-md flex items-center gap-0.5">
                              <AlertTriangle className="w-3 h-3 text-amber-600" />
                              시설미확인(UNKNOWN)
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Launch button */}
            <div className="p-4 bg-slate-100 border-t border-slate-200 shrink-0">
              <button
                onClick={() => void handleStartNavigation()}
                disabled={isLoading}
                className="w-full py-3.5 bg-blue-600 hover:bg-blue-700 text-white font-black text-[13.5px] rounded-full shadow-md flex items-center justify-center gap-1.5 cursor-pointer transform active:scale-95 transition-all"
              >
                <Navigation className="w-4 h-4 text-white rotate-45" />
                ETA 맞춤형 리스크 안내 시작
              </button>
            </div>
          </div>
        )}

        {/* SCREEN: ACTIVE STEP-BY-STEP NAVIGATION (F-NAV-01 / 02 / 03 / 04 / 05) */}
        {screen === "navigation" && navigationSession && origin && destination && (
          <NavigationScreen
            session={navigationSession}
            origin={origin}
            destination={destination}
            speedFactor={getSpeedMultiplier(profile)}
            onRouteChange={(session, route) => {
              setNavigationSession(session);
              setSelectedRoute(route);
            }}
            onFinish={handleCompleteNavigation}
            showToast={showToast}
          />
        )}

        {/* SCREEN: ARRIVAL & SPEED UPDATES (F-NAV-06 / F-PROFILE-03) */}
        {screen === "arrival" && selectedRoute && navigationCompletion && (
          <ArrivalScreen
            route={selectedRoute}
            previousSpeed={navigationStartSpeed}
            completion={navigationCompletion}
            onHome={() => setScreen("main")}
            onLogout={() => {
              clearDemoSession();
              setScreen("login");
              setUserEmail("");
            }}
          />
        )}

        {/* SCREEN: PROFILE SETTINGS EDITOR (F-PROFILE-02) */}
        {screen === "profile-edit" && (
          <ProfileScreen
            email={userEmail}
            initialProfile={profile}
            isEditMode={true}
            onComplete={(updated) => {
              setProfile(updated);
              setScreen("main");
            }}
            onCancel={() => setScreen("main")}
            onDeleteAccount={() => {
              clearDemoSession();
              setScreen("login");
              setUserEmail("");
            }}
            showToast={showToast}
          />
        )}

        {/* Floating toast notification wrapper */}
        {toastVisible && (
          <div className="absolute top-5 left-6 right-6 bg-slate-900/95 backdrop-blur text-white py-3 px-4 rounded-xl text-[12.5px] font-black z-50 shadow-xl border border-slate-700/50 flex items-center gap-2 animate-fade-in">
            <ShieldCheck className="w-4.5 h-4.5 text-blue-400 shrink-0" />
            <span className="leading-snug">{toastMessage}</span>
          </div>
        )}

      </div>
    </div>
  );
}
