import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "@/test/utils";

import { ApiError, apiRequest, onSessionExpired, setAccessToken } from "./api-client";

const fetchMock = () => vi.spyOn(globalThis, "fetch");
const authHeader = (call: unknown[]) =>
  ((call[1] as RequestInit).headers as Record<string, string>).Authorization;

afterEach(() => setAccessToken(null));

describe("apiRequest", () => {
  it("returns parsed JSON and calls the same-origin API with the token", async () => {
    setAccessToken("t1");
    const spy = fetchMock().mockResolvedValue(jsonResponse({ a: 1 }));
    await expect(apiRequest("/things", { query: { q: "x", empty: "", page: 2 } })).resolves.toEqual(
      { a: 1 },
    );
    expect(spy.mock.calls[0]?.[0]).toBe("/api/v1/things?q=x&page=2");
    expect(authHeader(spy.mock.calls[0]!)).toBe("Bearer t1");
  });

  it("throws ApiError with the backend error envelope", async () => {
    fetchMock().mockResolvedValue(
      jsonResponse({ error: { code: "conflict", message: "SKU band", request_id: "r1" } }, 409),
    );
    const err = await apiRequest("/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      status: 409,
      code: "conflict",
      message: "SKU band",
      requestId: "r1",
    });
  });

  it("maps network failures to a friendly Uzbek message", async () => {
    fetchMock().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(apiRequest("/x")).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("refreshes an expired token once and retries the request", async () => {
    setAccessToken("old");
    const spy = fetchMock().mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/admin/auth/refresh"))
        return jsonResponse({ access_token: "new", expires_at: "", admin: {} });
      const call = spy.mock.calls.at(-1)!;
      return authHeader(call) === "Bearer new"
        ? jsonResponse({ ok: true })
        : jsonResponse({ error: { code: "token_expired", message: "x" } }, 401);
    });
    await expect(apiRequest("/admin/orders")).resolves.toEqual({ ok: true });
    expect(spy.mock.calls.filter((c) => String(c[0]).endsWith("/refresh"))).toHaveLength(1);
  });

  it("uses a single refresh for parallel requests", async () => {
    setAccessToken("old");
    let refreshes = 0;
    const spy = fetchMock().mockImplementation(async (input) => {
      if (String(input).endsWith("/refresh")) {
        refreshes += 1;
        await new Promise((r) => setTimeout(r, 10));
        return jsonResponse({ access_token: "new", expires_at: "", admin: {} });
      }
      const call = spy.mock.calls.find((c) => c[0] === input && authHeader(c) === "Bearer new");
      return call
        ? jsonResponse({ ok: 1 })
        : jsonResponse({ error: { code: "unauthorized", message: "x" } }, 401);
    });
    await Promise.all([apiRequest("/a"), apiRequest("/b"), apiRequest("/c")]);
    expect(refreshes).toBe(1);
  });

  it("signals an expired session when the refresh fails", async () => {
    const listener = vi.fn();
    const off = onSessionExpired(listener);
    fetchMock().mockImplementation(async (input) =>
      String(input).endsWith("/refresh")
        ? jsonResponse({ error: { code: "invalid_refresh", message: "x" } }, 401)
        : jsonResponse(
            { error: { code: "unauthorized", message: "Avtorizatsiya talab qilinadi." } },
            401,
          ),
    );
    await expect(apiRequest("/admin/orders")).rejects.toMatchObject({ status: 401 });
    expect(listener).toHaveBeenCalledOnce();
    off();
  });

  it("does not refresh for anonymous calls such as login", async () => {
    const spy = fetchMock().mockResolvedValue(
      jsonResponse(
        { error: { code: "invalid_credentials", message: "Email yoki parol noto‘g‘ri." } },
        401,
      ),
    );
    await expect(
      apiRequest("/admin/auth/login", { method: "POST", body: {}, anonymous: true }),
    ).rejects.toMatchObject({
      code: "invalid_credentials",
    });
    expect(spy).toHaveBeenCalledOnce();
  });
});
