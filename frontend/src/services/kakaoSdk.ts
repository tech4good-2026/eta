export const KAKAO_SDK_TIMEOUT_MS = 5000;

export function isKakaoSdkReady(kakao: any): boolean {
  return Boolean(kakao?.maps?.Map);
}

export function shouldStopWaitingForKakao(startedAt: number, now: number): boolean {
  return now - startedAt >= KAKAO_SDK_TIMEOUT_MS;
}
