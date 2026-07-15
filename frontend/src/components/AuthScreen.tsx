import React, { useState } from "react";
import { Navigation, ShieldCheck, AlertTriangle } from "lucide-react";
import { signInDemo, signUpDemo } from "../utils/demoSession";

interface AuthScreenProps {
  onAuthSuccess: (email: string) => Promise<void>;
  showToast: (msg: string) => void;
}

export function AuthScreen({ onAuthSuccess, showToast }: AuthScreenProps) {
  const [isLogin, setIsLogin] = useState<boolean>(true);
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    if (!email.trim() || !password.trim()) {
      setErrorMsg("이메일과 비밀번호를 모두 입력해주세요.");
      return;
    }

    if (!isLogin && password.length < 8) {
      setErrorMsg("비밀번호는 최소 8자 이상이어야 합니다. (보안 정책 규정)");
      return;
    }

    try {
      if (isLogin) {
        const session = signInDemo(email, password);
        showToast("로그인 성공! 안전 이동 프로필 정보를 수집 중입니다.");
        await onAuthSuccess(session.email);
      } else {
        const guidance = signUpDemo();
        showToast(guidance.message);
        setEmail("test@eta.com");
        setPassword("");
        setIsLogin(true);
      }
    } catch (err: any) {
      if (err.message.includes("INVALID_CREDENTIALS")) {
        setErrorMsg("잘못된 비밀번호이거나 가입되지 않은 이메일입니다. (401 INVALID_CREDENTIALS)");
      } else {
        setErrorMsg(err.message || "인증 오류가 발생했습니다.");
      }
    }
  };

  return (
    <div className="flex-1 flex flex-col justify-between px-6 py-6 overflow-y-auto custom-scrollbar" id="view-login-screen">
      <div className="flex-1 flex flex-col justify-center">
        {/* Logo */}
        <div className="w-[58px] h-[58px] rounded-[18px] bg-blue-600 flex items-center justify-center mb-5 shadow-sm">
          <Navigation className="w-[28px] h-[28px] text-white rotate-45" />
        </div>

        <h1 className="text-[26px] font-black leading-[1.25] tracking-tight text-slate-900 mb-2">
          당신의 보행 템포로<br />
          계산한 맞춤 경로
        </h1>
        <p className="text-[13.5px] leading-relaxed text-slate-600 mb-6">
          보행 가이드 <b>ETA</b>는 휠체어, 유모차, 고령자 등 신체 상태에 알맞게 소요시간을 보정하고 우회 안전 경로를 유도합니다.
        </p>

        {/* Auth form Card */}
        <div className="bg-white rounded-[20px] p-5 border border-slate-200 shadow-sm mb-4">
          <div className="flex border-b border-slate-100 pb-3 mb-4 gap-4">
            <button
              onClick={() => {
                setIsLogin(true);
                setErrorMsg(null);
              }}
              className={`pb-1 text-[14.5px] font-bold transition-all ${
                isLogin ? "text-blue-600 border-b-2 border-blue-600" : "text-slate-400"
              }`}
            >
              로그인
            </button>
            <button
              onClick={() => {
                setIsLogin(false);
                setErrorMsg(null);
              }}
              className={`pb-1 text-[14.5px] font-bold transition-all ${
                !isLogin ? "text-blue-600 border-b-2 border-blue-600" : "text-slate-400"
              }`}
            >
              간편 가입
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3.5">
            <div>
              <label className="block text-[11px] font-bold text-slate-500 mb-1">이메일 계정</label>
              <input
                type="email"
                placeholder="example@eta.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full text-[13.5px] px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-blue-500 text-slate-950"
              />
            </div>
            <div>
              <label className="block text-[11px] font-bold text-slate-500 mb-1">비밀번호 {!isLogin && "(최소 8자 이상)"}</label>
              <input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full text-[13.5px] px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-blue-500 text-slate-950"
              />
            </div>

            {errorMsg && (
              <div className="p-2.5 bg-red-50 border border-red-100 text-red-500 text-[11.5px] font-semibold rounded-lg flex items-start gap-1.5 leading-snug">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                <span>{errorMsg}</span>
              </div>
            )}

            <button
              type="submit"
              className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-full font-bold text-[14px] shadow-sm transform active:scale-[0.98] transition-all cursor-pointer"
            >
              {isLogin ? "내 안전 속도로 로그인하기" : "데모 계정 안내받기"}
            </button>
          </form>
        </div>

        <div className="flex items-center gap-1.5 justify-center py-2 text-[12px] font-bold text-slate-500">
          <span className="bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded text-[9.5px] font-mono">가상체험</span>
          <span>아이디: <b className="text-slate-800">test@eta.com</b> / 비번: <b className="text-slate-800">password123</b></span>
        </div>
      </div>

      <div className="space-y-2 mt-4">
        <div className="p-3 bg-slate-100 rounded-xl flex items-start gap-2 text-[11px] text-slate-500 leading-relaxed">
          <ShieldCheck className="w-4.5 h-4.5 text-blue-600 shrink-0 mt-0.5" />
          <span>
            <b>개인정보 원칙 보장:</b> ETA 서비스는 사용자가 안내를 위해 수집하는 어떠한 실시간 GPS 동선 데이터도 외부에 저장하거나 임의 가공하지 않습니다.
          </span>
        </div>
      </div>
    </div>
  );
}
