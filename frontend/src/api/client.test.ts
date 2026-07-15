import { afterEach, describe, expect, it, vi } from "vitest";

import { requestJson } from "./client";

describe("requestJson", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the demo bearer token and JSON headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await requestJson("/users/me/profile");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/users/me/profile",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer demo-token",
          "Content-Type": "application/json",
        }),
      }),
    );
  });

  it("preserves the backend standard error code", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "TMAP_RATE_LIMITED",
              message: "호출 한도를 초과했습니다.",
              requestId: "req_001",
              details: { retryAfterSec: 60 },
            },
          }),
          { status: 429, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(requestJson("/routes/search")).rejects.toMatchObject({
      code: "TMAP_RATE_LIMITED",
      status: 429,
      requestId: "req_001",
    });
  });
});
