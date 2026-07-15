import React from "react";
import { Check, Home, LogOut, RefreshCw, ShieldCheck } from "lucide-react";

import type { ApiNavigationCompletion } from "../api/types";
import type { RouteInfo } from "../types";
import { PaceBar } from "./PaceBar";

interface ArrivalScreenProps {
  route: RouteInfo;
  previousSpeed: number;
  completion: ApiNavigationCompletion;
  savedReportCount?: number;
  onHome: () => void;
  onLogout: () => void;
}

export function ArrivalScreen({ route, previousSpeed, completion, savedReportCount, onHome, onLogout }: ArrivalScreenProps) {
  const speed = completion.walkingSpeed.walkingSpeedMps;
  const samples = completion.walkingSpeed.walkingSpeedSampleCount;
  const baseSpeed = completion.walkingSpeed.baseSpeedMps;
  const maxSpeed = completion.walkingSpeed.maxSpeedMps;

  return (
    <div className="flex-1 flex flex-col justify-between px-6 py-6 overflow-y-auto custom-scrollbar bg-slate-50" id="view-arrival-screen">
      <div className="text-center pt-3">
        <div className="w-[66px] h-[66px] rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto mb-4.5 border border-emerald-100 shadow-sm animate-pulse">
          <Check className="w-[32px] h-[32px]" />
        </div>
        <h1 className="text-[21.5px] font-black text-slate-900 mb-1">안전하게 완주했습니다!</h1>
        <p className="text-[13px] text-slate-500 leading-relaxed">
          장애물과 위험 구간을 무사히 우회하여 맞춤 목적지에 안착 완료했습니다.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-2 py-4">
        <div className="bg-white border border-slate-200 p-3 rounded-2xl text-center shadow-sm">
          <span className="block text-[10px] text-slate-400 font-bold mb-0.5">실제 완주 소요</span>
          <b className="text-[16px] font-mono text-blue-600">{route.personal}분</b>
        </div>
        <div className="bg-white border border-slate-200 p-3 rounded-2xl text-center shadow-sm">
          <span className="block text-[10px] text-slate-400 font-bold mb-0.5">환승 수단</span>
          <b className="text-[16px] font-mono text-blue-600">{route.transfers}회</b>
        </div>
        <div className="bg-white border border-slate-200 p-3 rounded-2xl text-center shadow-sm">
          <span className="block text-[10px] text-slate-400 font-bold mb-0.5">지불 요금</span>
          <b className="text-[16px] font-mono text-blue-600">
            {route.fare > 0 ? `${route.fare.toLocaleString()}원` : "0원"}
          </b>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-[22px] p-4.5 shadow-sm space-y-3">
        <h4 className="text-[13px] font-black text-slate-900 flex items-center gap-1.5">
          <RefreshCw className="w-4 h-4 text-amber-500" />
          ETA 걷기속도 정밀보정 리포트
        </h4>
        <p className="text-[11.5px] text-slate-500 leading-normal">
          안내 중 수집된 원본 좌표는 DB에 저장되지 않고 모두 폐기되었습니다.
          {completion.walkingSpeedUpdated
            ? " 유효한 보행 속도 표본만 프로필에 반영했습니다."
            : " 이번 안내에는 유효한 속도 표본이 없어 기존 속도를 유지했습니다."}
        </p>

        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100 grid grid-cols-2 gap-2 text-center text-slate-700 font-bold">
          <div className="border-r border-slate-200 py-0.5">
            <span className="block text-[9.5px] text-slate-400">이전 속도 산정</span>
            <span className="text-[13.5px] font-mono text-slate-800">{previousSpeed} m/s</span>
          </div>
          <div className="py-0.5">
            <span className="block text-[9.5px] text-slate-400">완료 후 속도</span>
            <span className="text-[13.5px] font-mono text-blue-600">{speed} m/s</span>
          </div>
        </div>

        <div className="flex items-center gap-2.5 pt-1 text-[11px] font-bold text-slate-500">
          <span>맞춤 보도 박자</span>
          <PaceBar speedFactor={speed / 1.3} />
          <span className="text-[9.5px] text-slate-400">표본: {samples}회</span>
        </div>

        {savedReportCount != null && savedReportCount > 0 && (
          <p className="text-[10.5px] font-bold text-emerald-600">
            ✓ 걸음 데이터가 이 기기에 저장되었습니다 (누적 리포트 {savedReportCount}회)
          </p>
        )}

        {baseSpeed != null && maxSpeed != null && (
          <div className="bg-blue-50/60 p-2.5 rounded-xl border border-blue-100 grid grid-cols-2 gap-2 text-center text-slate-700 font-bold">
            <div className="border-r border-blue-100 py-0.5">
              <span className="block text-[9.5px] text-slate-400">센서 기본속도</span>
              <span className="text-[13px] font-mono text-slate-800">{baseSpeed} m/s</span>
            </div>
            <div className="py-0.5">
              <span className="block text-[9.5px] text-slate-400">센서 최고속도</span>
              <span className="text-[13px] font-mono text-blue-600">{maxSpeed} m/s</span>
            </div>
          </div>
        )}
      </div>

      <div className="space-y-4 pt-4">
        <div className="p-3 bg-blue-50 border border-blue-100 rounded-xl flex items-start gap-2.5 text-[11px] text-blue-700 leading-normal">
          <ShieldCheck className="w-4.5 h-4.5 shrink-0 mt-0.5" />
          <span><b>위치정보 삭제 완료:</b> 세션 종료와 동시에 임시 GPS 정보가 소멸되었습니다.</span>
        </div>

        <div className="space-y-2">
          <button
            onClick={onHome}
            className="w-full py-3.5 bg-blue-600 hover:bg-blue-700 text-white rounded-full font-bold text-[14px] shadow-sm transform active:scale-[0.98] transition-all flex items-center justify-center gap-1.5 cursor-pointer"
          >
            <Home className="w-4.5 h-4.5" />
            메인 화면으로 돌아가기
          </button>
          <button
            onClick={onLogout}
            className="w-full py-3 bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 rounded-full font-bold text-[13.5px] flex items-center justify-center gap-1.5 cursor-pointer"
          >
            <LogOut className="w-4.5 h-4.5" />
            로그아웃 후 종료
          </button>
        </div>
      </div>
    </div>
  );
}
