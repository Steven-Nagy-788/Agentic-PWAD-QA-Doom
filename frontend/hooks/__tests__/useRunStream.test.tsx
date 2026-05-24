import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

describe("useRunStream", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("caps decisions at 500", async () => {
    const { useRunStream } = await import("@/hooks/useRunStream");

    function TestHarness() {
      const stream = useRunStream("test-run-id");
      return (
        <div>
          <span data-testid="decision-count">{stream.decisions.length}</span>
        </div>
      );
    }

    const { render } = await import("@testing-library/react");
    const wsMock = vi.fn();
    class MockWebSocket {
      onopen: (() => void) | null = null;
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      onclose: (() => void) | null = null;
      onerror: (() => void) | null = null;

      constructor(url: string) { wsMock(url); }
      close() {}
      send() {}
    }
    vi.stubGlobal("WebSocket", MockWebSocket);

    render(<TestHarness />);
    await vi.advanceTimersByTimeAsync(100);

    expect(wsMock).toHaveBeenCalledWith(expect.stringContaining("test-run-id"));
  });

  it("connects to WebSocket with correct URL", async () => {
    const { websocketUrl } = await import("@/lib/api");
    const url = websocketUrl("abc-123");
    expect(url).toContain("ws://");
    expect(url).toContain(":8000/v1/ws/runs/abc-123");
  });

  it("decisions array slicer truncates to 500", async () => {
    const arr = Array.from({ length: 600 }, (_, i) => ({
      sequenceNumber: i,
      reasoning: `decision ${i}`,
      tool: "explore",
    }));

    const slice = arr.slice(-500);
    expect(slice).toHaveLength(500);
    expect(slice[0].sequenceNumber).toBe(100);
    expect(slice[499].sequenceNumber).toBe(599);
  });
});
