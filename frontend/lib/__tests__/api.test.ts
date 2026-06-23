import { describe, it, expect, vi, afterEach } from "vitest";
import {
  assetUrl,
  apiGet,
  apiSend,
  apiRootGet,
  uploadWad,
  websocketBaseUrl,
  errorText,
  apiRootFromBase,
} from "../api";

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

describe("apiSend", () => {
  it("POSTs with JSON body on success", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ created: true }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiSend("/items", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "foo" }),
    });

    expect(result).toEqual({ created: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/items");
    expect(init.method).toBe("POST");
  });

  it("sends PATCH request", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ updated: true }),
      })),
    );

    const result = await apiSend("/items/1", {
      method: "PATCH",
      body: JSON.stringify({ name: "bar" }),
    });

    expect(result).toEqual({ updated: true });
  });

  it("returns undefined on 204 No Content", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 204,
      })),
    );

    const result = await apiSend("/items/1", { method: "DELETE" });
    expect(result).toBeUndefined();
  });

  it("throws on non-ok with JSON detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 422,
        statusText: "Unprocessable Entity",
        text: async () => JSON.stringify({ detail: "Invalid input" }),
      })),
    );

    await expect(apiSend("/items", { method: "POST" })).rejects.toThrow("Invalid input");
  });

  it("throws on non-ok with plain text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        text: async () => "Something went wrong",
      })),
    );

    await expect(apiSend("/items", { method: "POST" })).rejects.toThrow("Something went wrong");
  });
});

describe("apiRootGet", () => {
  it("returns parsed JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ version: "1.0" }),
      })),
    );

    const result = await apiRootGet("/status");
    expect(result).toEqual({ version: "1.0" });
  });

  it("throws on error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 403,
        statusText: "Forbidden",
        text: async () => "access denied",
      })),
    );

    await expect(apiRootGet("/admin")).rejects.toThrow("access denied");
  });
});

describe("uploadWad", () => {
  it("sends FormData and returns WadFile on success", async () => {
    const wadResult = {
      id: "wad-1",
      original_filename: "test.wad",
      file_size_bytes: 1024,
      sha256_hash: "abc123",
      validation_status: "valid",
      iwad_required: "doom2",
      uploaded_at: "2026-01-01T00:00:00Z",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => wadResult,
      })),
    );

    const file = new File(["content"], "test.wad", { type: "application/octet-stream" });
    const result = await uploadWad(file);

    expect(result).toEqual(wadResult);
    const [, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("throws on error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 413,
        statusText: "Payload Too Large",
        text: async () => JSON.stringify({ detail: "File too large" }),
      })),
    );

    const file = new File(["x".repeat(100)], "big.wad", { type: "application/octet-stream" });
    await expect(uploadWad(file)).rejects.toThrow("File too large");
  });
});

describe("websocketBaseUrl", () => {
  it("returns ws://localhost:8000 when origin is localhost", () => {
    vi.stubGlobal("window", { location: { origin: "http://localhost:3000" } });
    const url = websocketBaseUrl();
    expect(url.hostname).toBe("localhost");
    expect(url.port).toBe("8000");
  });

  it("uses WS_BASE for non-localhost origin", async () => {
    vi.stubGlobal("window", { location: { origin: "http://example.com" } });
    vi.stubEnv("NEXT_PUBLIC_WS_BASE", "wss://ws.example.com");
    vi.resetModules();
    const { websocketBaseUrl: wb } = await import("../api");
    const url = wb();
    expect(url.hostname).toBe("ws.example.com");
    expect(url.protocol).toBe("wss:");
  });

  it("uses absolute WS_BASE directly", async () => {
    vi.stubEnv("NEXT_PUBLIC_WS_BASE", "wss://custom-host:9090/path");
    vi.resetModules();
    const { websocketBaseUrl: wb } = await import("../api");
    const url = wb();
    expect(url.hostname).toBe("custom-host");
    expect(url.port).toBe("9090");
    expect(url.pathname).toBe("/path");
  });
});

describe("errorText", () => {
  it("extracts detail from JSON response", async () => {
    const response = {
      status: 422,
      statusText: "Unprocessable Entity",
      text: async () => JSON.stringify({ detail: "bad input" }),
    } as unknown as Response;

    expect(await errorText(response)).toBe("bad input");
  });

  it("returns raw text when JSON has no detail field", async () => {
    const response = {
      status: 500,
      statusText: "Internal Server Error",
      text: async () => JSON.stringify({ message: "oops" }),
    } as unknown as Response;

    const result = await errorText(response);
    expect(result).toBe(JSON.stringify({ message: "oops" }));
  });

  it("returns text as-is for non-JSON response", async () => {
    const response = {
      status: 502,
      statusText: "Bad Gateway",
      text: async () => "upstream error",
    } as unknown as Response;

    expect(await errorText(response)).toBe("upstream error");
  });
});

describe("apiRootFromBase", () => {
  it("strips /v1 suffix from /api/v1", () => {
    expect(apiRootFromBase("/api/v1")).toBe("/api");
  });

  it("strips trailing slash and /v1 from /api/v1/", () => {
    expect(apiRootFromBase("/api/v1/")).toBe("/api");
  });

  it("strips /v1 from a custom base path", () => {
    expect(apiRootFromBase("/custom/api/v1")).toBe("/custom/api");
  });
});
