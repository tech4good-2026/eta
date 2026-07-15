export const DEMO_EMAIL = "test@eta.com";
export const DEMO_PASSWORD = "password123";
export const DEMO_TOKEN = "demo-token";

const SESSION_KEY = "eta_demo_session";

export interface DemoSession {
  email: string;
  token: string;
}

export function signInDemo(email: string, password: string): DemoSession {
  if (email.trim().toLowerCase() !== DEMO_EMAIL || password !== DEMO_PASSWORD) {
    throw new Error("INVALID_CREDENTIALS");
  }
  const session = { email: DEMO_EMAIL, token: DEMO_TOKEN };
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

export function signUpDemo() {
  return { message: `데모 계정 ${DEMO_EMAIL} / ${DEMO_PASSWORD}으로 로그인해 주세요.` };
}

export function getDemoSession(): DemoSession | null {
  const raw = localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as DemoSession;
    return session.token === DEMO_TOKEN && session.email === DEMO_EMAIL ? session : null;
  } catch {
    clearDemoSession();
    return null;
  }
}

export function clearDemoSession() {
  localStorage.removeItem(SESSION_KEY);
}
