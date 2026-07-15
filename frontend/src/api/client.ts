import type {
  ApiLocationSample,
  ApiNavigationCompletion,
  ApiNavigationSession,
  ApiNavigationUpdate,
  ApiRerouteRequest,
  ApiRouteSearchRequest,
  ApiRouteSearchResponse,
  ApiUpdateProfileRequest,
  ApiUserProfile,
} from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/$/, "");
const DEMO_TOKEN = "demo-token";

export class ApiClientError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
    public readonly requestId?: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

export async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${DEMO_TOKEN}`,
      ...init.headers,
    },
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error;
    throw new ApiClientError(
      error?.code || "NETWORK_ERROR",
      error?.message || "서버 요청을 처리하지 못했습니다.",
      response.status,
      error?.requestId,
      error?.details,
    );
  }
  return body as T;
}

export const api = {
  getProfile: () => requestJson<ApiUserProfile>("/users/me/profile"),
  updateProfile: (profile: ApiUpdateProfileRequest) =>
    requestJson<ApiUserProfile>("/users/me/profile", {
      method: "PUT",
      body: JSON.stringify(profile),
    }),
  searchRoutes: (request: ApiRouteSearchRequest) =>
    requestJson<ApiRouteSearchResponse>("/routes/search", {
      method: "POST",
      body: JSON.stringify(request),
    }),
  startNavigation: (routeId: string) =>
    requestJson<ApiNavigationSession>("/navigation/sessions", {
      method: "POST",
      body: JSON.stringify({ routeId }),
    }),
  sendPosition: (sessionId: string, sample: ApiLocationSample) =>
    requestJson<ApiNavigationUpdate>(`/navigation/sessions/${sessionId}/position`, {
      method: "POST",
      body: JSON.stringify(sample),
    }),
  rerouteNavigation: (sessionId: string, request: ApiRerouteRequest) =>
    requestJson<ApiNavigationSession>(`/navigation/sessions/${sessionId}/reroute`, {
      method: "POST",
      body: JSON.stringify(request),
    }),
  completeNavigation: (sessionId: string, reason: "ARRIVED" | "USER_STOPPED" = "ARRIVED") =>
    requestJson<ApiNavigationCompletion>(`/navigation/sessions/${sessionId}/complete`, {
      method: "POST",
      body: JSON.stringify({ reason, completedAt: new Date().toISOString() }),
    }),
};
