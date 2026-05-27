import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    queueMicrotask(() => this.onopen?.());
  }

  close() {}
  send() {}
}

function liveSnapshot() {
  return {
    run: {
      id: "test-run-id",
      wad_file_id: "wad-id",
      map_name: "MAP01",
      difficulty_level: 3,
      iwad_used: "doom2.wad",
      llm_model: "test-model",
      max_ticks: 1000,
      status: "running",
      created_at: "2026-01-01T00:00:00Z",
    },
    state: null,
    decisions: [],
    trace: [],
    events: [],
    position_trail: [],
    defects: [],
    usage: {
      run_id: "test-run-id",
      model: "test-model",
      total_llm_calls: 0,
      total_prompt_tokens: 0,
      total_completion_tokens: 0,
      total_tokens: 0,
      estimated_cost_usd: 0,
      per_decision_avg_cost_usd: 0,
    },
    progress_metrics: {},
    agent_quality_flags: {},
    report_status: { status: "pending" },
    run_history: null,
  };
}

describe("useRunStream", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => liveSnapshot(),
        text: async () => "",
      })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("connects to WebSocket with correct URL", async () => {
    const { websocketUrl } = await import("@/lib/api");
    const url = websocketUrl("abc-123");
    expect(url).toContain("ws://");
    expect(url).toContain(":8000/v1/ws/runs/abc-123");
  });

  it("loads snapshot and connects without waiting for new stream data", async () => {
    const { useRunStream } = await import("@/hooks/useRunStream");

    function TestHarness() {
      const stream = useRunStream("test-run-id");
      return (
        <div>
          <span data-testid="snapshot-run">{stream.snapshot?.run.map_name ?? ""}</span>
          <span data-testid="connected">{String(stream.connected)}</span>
        </div>
      );
    }

    render(<TestHarness />);
    await waitFor(() => expect(screen.getByTestId("snapshot-run").textContent).toBe("MAP01"));
    await waitFor(() => expect(screen.getByTestId("connected").textContent).toBe("true"));

    expect(MockWebSocket.instances[0]?.url).toContain("test-run-id");
  });

  it("dedupes token totals for replayed decision messages", async () => {
    const { useRunStream } = await import("@/hooks/useRunStream");

    function TestHarness() {
      const stream = useRunStream("test-run-id");
      return (
        <div>
          <span data-testid="tokens">{stream.tokenTotals.totalTokens}</span>
          <span data-testid="cost">{stream.tokenTotals.totalCost.toFixed(6)}</span>
          <span data-testid="decision-count">{stream.tokenTotals.decisionCount}</span>
        </div>
      );
    }

    render(<TestHarness />);
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    const socket = MockWebSocket.instances[0];
    const payload = JSON.stringify({
      type: "llm_decision",
      sequence_number: 4,
      tick: 120,
      reasoning_summary: "Check the hallway.",
      mcp_tool: "explore",
      llm_input_tokens: 100,
      llm_output_tokens: 25,
      llm_cost_estimate_usd: 0.0015,
    });

    act(() => {
      socket.onmessage?.({ data: payload } as MessageEvent<string>);
      socket.onmessage?.({ data: payload } as MessageEvent<string>);
    });

    expect(screen.getByTestId("tokens").textContent).toBe("125");
    expect(screen.getByTestId("cost").textContent).toBe("0.001500");
    expect(screen.getByTestId("decision-count").textContent).toBe("1");
  });

  it("reports invalid WebSocket JSON without throwing", async () => {
    const { useRunStream } = await import("@/hooks/useRunStream");

    function TestHarness() {
      const stream = useRunStream("test-run-id");
      return <span data-testid="error">{stream.error ?? ""}</span>;
    }

    render(<TestHarness />);
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));

    act(() => {
      MockWebSocket.instances[0].onmessage?.({ data: "not-json" } as MessageEvent<string>);
    });

    expect(screen.getByTestId("error").textContent).toContain("invalid live stream payload");
  });

  it("decisions array slicer truncates to 500", () => {
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
