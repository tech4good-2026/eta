import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearDemoSession,
  getDemoSession,
  signInDemo,
  signUpDemo,
} from "./demoSession";

class MemoryStorage implements Storage {
  private values = new Map<string, string>();

  get length() {
    return this.values.size;
  }

  clear() {
    this.values.clear();
  }

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  key(index: number) {
    return [...this.values.keys()][index] ?? null;
  }

  removeItem(key: string) {
    this.values.delete(key);
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

describe("demo session", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", new MemoryStorage());
  });

  it("only accepts the documented demo account and stores no password", () => {
    expect(signInDemo("test@eta.com", "password123")).toEqual({
      email: "test@eta.com",
      token: "demo-token",
    });
    expect(getDemoSession()).toEqual({ email: "test@eta.com", token: "demo-token" });
    expect(localStorage.getItem("eta_demo_session")).not.toContain("password123");
    expect(() => signInDemo("other@eta.com", "password123")).toThrow("INVALID_CREDENTIALS");
  });

  it("keeps signup as guidance only and does not create an account", () => {
    expect(signUpDemo()).toEqual({
      message: "데모 계정 test@eta.com / password123으로 로그인해 주세요.",
    });
    expect(getDemoSession()).toBeNull();
  });

  it("clears the token on logout", () => {
    signInDemo("test@eta.com", "password123");
    clearDemoSession();
    expect(getDemoSession()).toBeNull();
  });
});
