import type { ApiNavigationCompletion } from "../api/types";

export interface WalkReport {
  completedAt: string;
  walkingSpeedMps: number;
  baseSpeedMps?: number;
  maxSpeedMps?: number;
  sampleCount: number;
  updated: boolean;
}

const STORAGE_KEY = "eta.walkReports";
const MAX_REPORTS = 30;

export function loadWalkReports(storage: Storage | undefined = globalThis.localStorage): WalkReport[] {
  if (!storage) return [];
  try {
    const raw = storage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/** 안내 완료 리포트의 걸음(보행 속도) 데이터를 기기에 저장한다. 좌표는 저장하지 않는다. */
export function saveWalkReport(
  completion: ApiNavigationCompletion,
  storage: Storage | undefined = globalThis.localStorage,
): WalkReport[] {
  const report: WalkReport = {
    completedAt: completion.completedAt,
    walkingSpeedMps: completion.walkingSpeed.walkingSpeedMps,
    baseSpeedMps: completion.walkingSpeed.baseSpeedMps ?? undefined,
    maxSpeedMps: completion.walkingSpeed.maxSpeedMps ?? undefined,
    sampleCount: completion.walkingSpeed.walkingSpeedSampleCount,
    updated: completion.walkingSpeedUpdated,
  };
  const reports = [report, ...loadWalkReports(storage)].slice(0, MAX_REPORTS);
  try {
    storage?.setItem(STORAGE_KEY, JSON.stringify(reports));
  } catch {
    // 저장 공간 문제 등은 조용히 무시한다(리포트 표시는 계속 동작).
  }
  return reports;
}
