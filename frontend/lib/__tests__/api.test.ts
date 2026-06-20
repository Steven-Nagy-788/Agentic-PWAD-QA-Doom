import { describe, it, expect, vi, afterEach } from "vitest";
import { assetUrl, apiGet } from "../api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("websocketUrl", () => {
  it("constructs ws:// from local origin with /api/v1 base", async () => {
    vi.stubGlobal("window", { location: { origin: "http://localhost:3000" } });
    const { websocketUrl } = await import("../api");
    const url = websocketUrl("abc-123");
    expect(url).toContain("ws://");
    expect(url).toContain(":8000/");
    expect(url).toContain("/ws/runs/abc-123");
  });
});

describe("assetUrl", () => {
  it("returns undefined for null", () => {
    expect(assetUrl(null)).toBeUndefined();
  });

  it("returns undefined for undefined", () => {
    expect(assetUrl(undefined)).toBeUndefined();
  });

  it("returns undefined for empty string", () => {
    expect(assetUrl("")).toBeUndefined();
  });

  it("prepends API_BASE for relative paths", () => {
    const result = assetUrl("/v1/wads/123/file");
    expect(result).toContain("/v1/wads/123/file");
  });

  it("returns absolute URLs unchanged", () => {
    expect(assetUrl("https://cdn.example.com/img.png")).toBe("https://cdn.example.com/img.png");
  });
});

describe("apiGet", () => {
  it("throws on non-ok response with text body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 404,
        statusText: "Not Found",
        text: async () => "not found",
      })),
    );

    await expect(apiGet("/nonexistent")).rejects.toThrow("not found");
  });

  it("returns parsed json on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ id: "123", name: "test" }),
      })),
    );

    const result = await apiGet("/test");
    expect(result).toEqual({ id: "123", name: "test" });
  });
});
