import React, { useState, useEffect } from "react";
import { ArrowLeft, Check, Info, ShieldAlert, Trash2 } from "lucide-react";
import { UserProfile, CHAR_OPTIONS, DEVICE_OPTIONS } from "../types";

interface ProfileScreenProps {
  email: string;
  initialProfile: UserProfile;
  isEditMode?: boolean;
  onComplete: (updatedProfile: UserProfile) => Promise<void> | void;
  onCancel?: () => void;
  onDeleteAccount?: () => void;
  showToast: (msg: string) => void;
}

export function ProfileScreen({
  email,
  initialProfile,
  isEditMode = false,
  onComplete,
  onCancel,
  onDeleteAccount,
  showToast
}: ProfileScreenProps) {
  const [step, setStep] = useState<number>(1);
  const [chars, setChars] = useState<string[]>(initialProfile.chars || []);
  const [devices, setDevices] = useState<string[]>(initialProfile.devices || []);
  const [avoidStairs, setAvoidStairs] = useState<boolean>(initialProfile.avoidStairs || false);
  const [elevatorRequired, setElevatorRequired] = useState<boolean>(initialProfile.elevatorRequired || false);
  const [lowFloorBusRequired, setLowFloorBusRequired] = useState<boolean>(initialProfile.lowFloorBusRequired || false);
  const [avoidSteepSlopes, setAvoidSteepSlopes] = useState<boolean>(initialProfile.avoidSteepSlopes || false);

  // Auto configure toggles based on mobility aid selection to make it extremely smart!
  useEffect(() => {
    if (!isEditMode) {
      if (devices.includes("MANUAL_WHEELCHAIR") || devices.includes("POWER_WHEELCHAIR")) {
        setAvoidStairs(true);
        setElevatorRequired(true);
        setLowFloorBusRequired(true);
        setAvoidSteepSlopes(true);
      } else if (devices.includes("STROLLER")) {
        setAvoidStairs(true);
        setElevatorRequired(true);
        setLowFloorBusRequired(true);
      } else if (devices.includes("WALKER") || devices.includes("CANE")) {
        setAvoidStairs(true);
        setAvoidSteepSlopes(true);
      }
    }
  }, [devices, isEditMode]);

  const toggleChar = (code: string) => {
    setChars((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    );
  };

  const toggleDevice = (code: string) => {
    if (code === "NONE") {
      setDevices(["NONE"]);
    } else {
      setDevices((prev) => {
        const filtered = prev.filter((d) => d !== "NONE");
        return filtered.includes(code) ? filtered.filter((d) => d !== code) : [...filtered, code];
      });
    }
  };

  const handleNext = () => {
    if (step < 3) {
      setStep(step + 1);
    } else {
      handleSave();
    }
  };

  const handleSave = async () => {
    if (chars.length === 0) {
      showToast("하나 이상의 사용자 유형을 체크해야 신체 프로필 설계가 완성됩니다.");
      setStep(1);
      return;
    }

    try {
      const updatedProfile: UserProfile = {
        ...initialProfile,
        chars,
        devices,
        avoidStairs,
        elevatorRequired,
        lowFloorBusRequired,
        avoidSteepSlopes
      };
      await onComplete(updatedProfile);
      showToast(isEditMode ? "개인용 이동 특성 및 경고 세팅이 수정되었습니다." : "최초 신체 맞춤 ETA 프로필 등록 성공!");
    } catch (e: any) {
      showToast(e.message || "프로필 저장 중 오류가 발생했습니다.");
    }
  };

  const handleDelete = () => {
    if (confirm("정말로 회원을 탈퇴하시겠습니까? 프로필, 계정 및 저장된 평균 보행 속도 학습 정보가 전량 즉시 파기되며 복구가 불가능합니다.")) {
      try {
        showToast("데모 계정은 탈퇴할 수 없어 현재 로그인 정보만 삭제합니다.");
        if (onDeleteAccount) onDeleteAccount();
      } catch (err) {
        showToast("탈퇴 처리 중 실패했습니다.");
      }
    }
  };

  // Label resolving helpers
  const getCharLabel = (code: string) => CHAR_OPTIONS.find((c) => c.code === code)?.label || code;
  const getDeviceLabel = (code: string) => DEVICE_OPTIONS.find((d) => d.code === code)?.label || code;

  return (
    <div className="flex-1 min-h-0 flex flex-col px-6 py-5 bg-slate-50 overflow-y-auto custom-scrollbar" id="view-profile-screen">
      {/* Progress top indicator */}
      {!isEditMode && (
        <div className="flex justify-between gap-1.5 w-full mb-5">
          <span className={`h-1 flex-1 rounded ${step >= 1 ? "bg-blue-600" : "bg-slate-200"}`}></span>
          <span className={`h-1 flex-1 rounded ${step >= 2 ? "bg-blue-600" : "bg-slate-200"}`}></span>
          <span className={`h-1 flex-1 rounded ${step >= 3 ? "bg-blue-600" : "bg-slate-200"}`}></span>
        </div>
      )}

      {/* Header controls */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          {(isEditMode || step > 1) && (
            <button
              onClick={() => {
                if (step > 1) {
                  setStep(step - 1);
                } else if (isEditMode && onCancel) {
                  onCancel();
                }
              }}
              className="w-8 h-8 rounded-full bg-white flex items-center justify-center shadow-sm border border-slate-200"
            >
              <ArrowLeft className="w-4 h-4 text-slate-800" />
            </button>
          )}
          <span className="text-[12.5px] font-bold text-slate-600">
            {isEditMode ? "프로필 수정" : `STEP 0${step} / 03`}
          </span>
        </div>

        {isEditMode && (
          <button
            onClick={handleDelete}
            className="text-red-500 hover:text-red-600 flex items-center gap-1.5 text-[12px] font-bold py-1 px-2.5 rounded-lg hover:bg-red-50 border border-transparent hover:border-red-100 transition-all cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            회원 탈퇴
          </button>
        )}
      </div>

      <div className="flex-1 flex flex-col justify-between">
        {/* STEP 1: PHYSICAL TYPE */}
        {(isEditMode ? step === 1 : step === 1) && (
          <div className="space-y-4">
            <div>
              <h2 className="text-[19.5px] font-black text-slate-900 leading-snug">
                이동 시 해당하는 신체 특성이 있으신가요?
              </h2>
              <p className="text-[12.5px] text-slate-500 mt-1">
                복수 선택이 가능합니다. 이 선택 정보는 사용자 속도를 조정하고 교통약자 맞춤 노선을 분석하는 핵심 정보가 됩니다.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-2.5" id="profile-chars-container">
              {CHAR_OPTIONS.map((opt) => {
                const isSelected = chars.includes(opt.code);
                return (
                  <button
                    key={opt.code}
                    onClick={() => toggleChar(opt.code)}
                    className={`p-3 rounded-xl border-[1.5px] text-left font-bold transition-all transform active:scale-95 flex flex-col justify-between h-[82px] cursor-pointer ${
                      isSelected
                        ? "bg-blue-50 border-blue-600 text-blue-600"
                        : "bg-white border-slate-200 text-slate-600 hover:border-blue-600"
                    }`}
                  >
                    <span className="text-[13.5px]">{opt.label}</span>
                    {isSelected && <Check className="w-4 h-4 text-blue-600 self-end" />}
                  </button>
                );
              })}
            </div>

            <div className="p-3 bg-blue-50 border border-blue-100 rounded-xl text-[11.5px] text-blue-600 leading-relaxed flex items-start gap-2">
              <Info className="w-4 h-4 shrink-0 mt-0.5" />
              <span><b>알림:</b> 보조 기구 세부 설정(휠체어, 유모차 등)은 다음 장에서 이어집니다.</span>
            </div>
          </div>
        )}

        {/* STEP 2: MOBILITY AID */}
        {step === 2 && (
          <div className="space-y-4">
            <div>
              <h2 className="text-[19.5px] font-black text-slate-900 leading-snug">
                현재 일상적으로 사용하는 보조기구가 있나요?
              </h2>
              <p className="text-[12.5px] text-slate-500 mt-1">
                휠체어/유모차 등의 수단은 계단이나 극단적인 경사로, 지하철 리프트 탑승 필수 여부를 파악하는 기준이 됩니다.
              </p>
            </div>

            <div className="flex flex-wrap gap-2" id="profile-devices-container">
              {DEVICE_OPTIONS.map((opt) => {
                const isSelected = devices.includes(opt.code);
                return (
                  <button
                    key={opt.code}
                    onClick={() => toggleDevice(opt.code)}
                    className={`py-2.5 px-4.5 rounded-full text-[13px] font-bold border-[1.5px] transition-all transform active:scale-95 cursor-pointer ${
                      isSelected
                        ? "bg-blue-600 border-blue-600 text-white"
                        : "bg-white border-slate-200 text-slate-600 hover:border-blue-500"
                    }`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>

            <div className="p-3 bg-amber-50 border border-amber-100 rounded-xl text-[11.5px] text-amber-700 leading-relaxed flex items-start gap-2">
              <Info className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                <b>자동 분석 기능:</b> 휠체어나 유모차 선택 시, 다음 챕터의 계단 회피 및 엘리베이터 필수 옵션이 지능형 안전모드로 자동 켜집니다.
              </span>
            </div>
          </div>
        )}

        {/* STEP 3: ACCESSIBILITY PREFERENCES */}
        {step === 3 && (
          <div className="space-y-4">
            <div>
              <h2 className="text-[19.5px] font-black text-slate-900 leading-snug">
                상세 접근성 선호 조건을 설정하세요
              </h2>
              <p className="text-[12.5px] text-slate-500 mt-1">
                사용자 선호도와 필수 규정에 의거하여 안전 노선을 선별하고 차트의 정렬 순서 우선순위를 결정합니다.
              </p>
            </div>

            <div className="space-y-3 bg-white p-4 rounded-2xl border border-slate-200">
              <div className="flex items-center justify-between py-1.5">
                <div>
                  <h4 className="text-[13.5px] font-bold text-slate-900">계단 경로 회피</h4>
                  <p className="text-[11px] text-slate-400">도보 안내 시 계단이 포함된 우회길 무조건 유도</p>
                </div>
                <input
                  type="checkbox"
                  checked={avoidStairs}
                  onChange={(e) => setAvoidStairs(e.target.checked)}
                  className="w-5 h-5 accent-blue-600 cursor-pointer"
                />
              </div>

              <div className="border-t border-slate-100 my-2"></div>

              <div className="flex items-center justify-between py-1.5">
                <div>
                  <h4 className="text-[13.5px] font-bold text-slate-900">지하철 엘리베이터 필수</h4>
                  <p className="text-[11px] text-slate-400">환승 및 진출입 시 리프트 대신 엘리베이터 중심 안내</p>
                </div>
                <input
                  type="checkbox"
                  checked={elevatorRequired}
                  onChange={(e) => setElevatorRequired(e.target.checked)}
                  className="w-5 h-5 accent-blue-600 cursor-pointer"
                />
              </div>

              <div className="border-t border-slate-100 my-2"></div>

              <div className="flex items-center justify-between py-1.5">
                <div>
                  <h4 className="text-[13.5px] font-bold text-slate-900">저상 버스 필수 탑승</h4>
                  <p className="text-[11px] text-slate-400">계단식 버스 제외 및 전 차량 슬로프 탑승 지원 버스</p>
                </div>
                <input
                  type="checkbox"
                  checked={lowFloorBusRequired}
                  onChange={(e) => setLowFloorBusRequired(e.target.checked)}
                  className="w-5 h-5 accent-blue-600 cursor-pointer"
                />
              </div>

              <div className="border-t border-slate-100 my-2"></div>

              <div className="flex items-center justify-between py-1.5">
                <div>
                  <h4 className="text-[13.5px] font-bold text-slate-900">급경사 구간 회피</h4>
                  <p className="text-[11px] text-slate-400">휠체어 미끄러짐 방지를 위한 4도 초과 언덕길 회피</p>
                </div>
                <input
                  type="checkbox"
                  checked={avoidSteepSlopes}
                  onChange={(e) => setAvoidSteepSlopes(e.target.checked)}
                  className="w-5 h-5 accent-blue-600 cursor-pointer"
                />
              </div>
            </div>

            <div className="p-3 bg-red-50 border border-red-100 rounded-xl text-[11px] text-red-600 leading-relaxed flex items-start gap-1.5">
              <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                <b>안전 보증 disclaimer:</b> 정보 미확인(`UNKNOWN`) 인프라의 가동 불가 우려 등으로 인해 안내 내용이 실시간 도로 상태와 완벽히 다를 수 있음을 주의바랍니다.
              </span>
            </div>
          </div>
        )}

        {/* Action Controls */}
        <div className="space-y-2 mt-5">
          {isEditMode ? (
            <button
              onClick={step === 3 ? handleSave : () => setStep(step + 1)}
              disabled={chars.length === 0}
              className="w-full py-3.5 bg-blue-600 hover:bg-blue-700 text-white disabled:bg-slate-300 rounded-full font-bold text-[14px] shadow-sm transform active:scale-[0.98] transition-all cursor-pointer"
            >
              {step === 3 ? "프로필 변경 사항 적용 및 보도 재산출" : "다음 설정으로"}
            </button>
          ) : (
            <div className="flex gap-2">
              {step > 1 && (
                <button
                  onClick={() => setStep(step - 1)}
                  className="w-1/3 py-3.5 bg-white border border-slate-300 text-slate-700 rounded-full font-bold text-[14px] transform active:scale-[0.98] transition-all cursor-pointer"
                >
                  이전
                </button>
              )}
              <button
                onClick={handleNext}
                disabled={step === 1 && chars.length === 0}
                className="flex-1 py-3.5 bg-blue-600 hover:bg-blue-700 text-white disabled:bg-slate-300 rounded-full font-bold text-[14px] shadow-sm transform active:scale-[0.98] transition-all cursor-pointer"
              >
                {step === 3 ? "맞춤형 이동 분석 시작" : "다음 단계로"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
