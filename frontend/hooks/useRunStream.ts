"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Decision, Defect, PositionSample, Run, TraceEntry, UsageStats, ReportStatus, apiGet, websocketUrl } from "@/lib/api";

export type RunStreamMessage = {
  type: string;
  tick?: number;
  status?: string;
  sequence_number?: number;
  reasoning_summary?: string;
  mcp_tool?: string;
  mcp_params?: Record<string, unknown>;
  mcp_input?: Record<string, unknown>;
  mcp_output?: Record<string, unknown>;
  mcp_stop_reason?: string;
  frame_b64?: string;
  mime_type?: string;
  health?: number;
  armor?: number;
  kills?: number;
  secrets?: number;
  ammo?: { bullets?: number; shells?: number; rockets?: number; cells?: number };
  position?: { x: number; y: number; angle?: number };
  event_type?: string;
  progress_score?: number;
  report_status?: string;
  defect_type?: string;
  title?: string;
  severity?: number;
  fingerprint?: string;
  detected_at_tick?: number;
  llm_duration_ms?: number;
  llm_input?: Record<string, unknown>;
  llm_raw_output?: Record<string, unknown>;
  visited_cells?: Record<string, number>;
  visited_cell_size?: number;
  mcp_duration_ms?: number;
  decision_source?: string;
  validation_rejection?: string;
  llm_input_tokens?: number;
  llm_output_tokens?: number;
  llm_cost_estimate_usd?: number;
  same_run_memory?: SameRunMemory;
};

export type SameRunMemory = {
  older_milestones: {
    compacted_action_count: number;
    tool_counts: Record<string, number>;
    stop_reason_counts: Record<string, number>;
    completed_targets: Record<string, unknown>;
    failed_targets: Record<string, unknown>;
    checkpoints: { tick: number; event: string; pos: { x: number; y: number } }[];
    hypotheses: string[];
  };
  recent_actions: SameRunAction[];
  aggregates: {
    total_actions: number;
    tool_counts: Record<string, number>;
    stop_reason_counts: Record<string, number>;
    combat: RunHistoryCombat;
    progress_score: number;
    meaningful_progress_events: number;
    runtime_warnings: string[];
  };
  budget: {
    total_ticks: number;
    ticks_used: number;
    ticks_remaining: number;
    decisions_made: number;
    avg_ticks_per_decision: number;
    estimated_decisions_remaining: number;
  };
};

export type SameRunAction = {
  seq: number;
  tick_before: number;
  tick_after: number;
  tool: string;
  stop_reason: string;
  result: string;
  params: Record<string, unknown>;
  key_findings: string;
  reasoning: string;
  decision_source: string;
  validation_rejection?: string | null;
  target?: Record<string, unknown>;
  movement?: Record<string, unknown>;
  collection?: Record<string, unknown>;
  combat?: Record<string, unknown>;
  state_delta?: Record<string, unknown>;
  final_position?: { x?: number; y?: number; angle?: number };
  llm_ms: number;
  mcp_ms: number;
};

export type RunHistoryCombat = {
  total_engagements: number;
  total_kills: number;
  total_shots: number;
  total_hits: number;
  enemies_engaged: { id: number; name: string; weapon: string; shots: number; hits: number; killed: boolean }[];
  weapon_performance: Record<string, { shots: number; hits: number; kills: number; accuracy: number }>;
};

export type LiveDecision = {
  sequenceNumber: number;
  tick?: number;
  reasoning?: string;
  tool?: string;
  stopReason?: string;
  params?: Record<string, unknown>;
  mcpOutput?: Record<string, unknown>;
  llmInput?: Record<string, unknown>;
  llmOutput?: Record<string, unknown>;
  decisionSource?: string;
  validationRejection?: string;
  mcpDurationMs?: number;
  llmDurationMs?: number;
  llmInputTokens?: number;
  llmOutputTokens?: number;
  llmCostEstimateUsd?: number;
};

export type SessionTokenTotals = {
  totalPrompt: number;
  totalCompletion: number;
  totalTokens: number;
  totalCost: number;
  decisionCount: number;
};

export type LiveSnapshot = {
  run: Run;
  state?: RunStreamMessage | null;
  decisions: Decision[];
  trace: TraceEntry[];
  events: TraceEntry[];
  position_trail: PositionSample[];
  defects: Defect[];
  usage: UsageStats;
  progress_metrics: Record<string, unknown>;
  agent_quality_flags: Record<string, unknown>;
  report_status: ReportStatus;
  same_run_memory: SameRunMemory | null;
  visited_cells?: Record<string, number>;
  visited_cell_size?: number;
};

export type RunStreamPhase = "idle" | "loading_snapshot" | "connecting" | "connected" | "reconnecting" | "closed" | "error";

const EMPTY_TOTALS: SessionTokenTotals = {
  totalPrompt: 0,
  totalCompletion: 0,
  totalTokens: 0,
  totalCost: 0,
  decisionCount: 0,
};

export function useRunStream(runId?: string) {
  const [messages, setMessages] = useState<RunStreamMessage[]>([]);
  const [frame, setFrame] = useState<string | null>(null);
  const [state, setState] = useState<RunStreamMessage | null>(null);
  const [decisions, setDecisions] = useState<LiveDecision[]>([]);
  const [defects, setDefects] = useState<Defect[]>([]);
  const [connected, setConnected] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [retryDelay, setRetryDelay] = useState(0);
  const [lastMessageAt, setLastMessageAt] = useState(0);
  const [sameRunMemory, setSameRunMemory] = useState<SameRunMemory | null>(null);
  const [visitedCells, setVisitedCells] = useState<Record<string, number>>({});
  const [visitedCellSize, setVisitedCellSize] = useState(256);
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);
  const [phase, setPhase] = useState<RunStreamPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const retryRef = useRef(0);
  const socketRef = useRef<WebSocket | null>(null);
  const lastFrameRef = useRef("");

  useEffect(() => {
    if (!runId) {
      return;
    }
    let cancelled = false;
    Promise.resolve()
      .then(() => {
        if (cancelled) return null;
        setPhase("loading_snapshot");
        setError(null);
        return apiGet<LiveSnapshot>(`/runs/${runId}/live-snapshot`);
      })
      .then((data) => {
        if (cancelled || !data) return;
        setSnapshot(data);
        setState(data.state ?? null);
        setSameRunMemory(data.same_run_memory ?? null);
        setVisitedCells(data.visited_cells ?? {});
        setVisitedCellSize(data.visited_cell_size ?? 256);
        setDefects(data.defects ?? []);
        setDecisions(data.decisions.map(decisionFromSnapshot).slice(-500));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      setPhase(retryRef.current > 0 ? "reconnecting" : "connecting");
      const socket = new WebSocket(websocketUrl(runId));
      socketRef.current = socket;
      socket.onopen = () => {
        retryRef.current = 0;
        setRetryCount(0);
        setRetryDelay(0);
        setConnected(true);
        setPhase("connected");
        setError(null);
      };
      socket.onmessage = (event) => {
        setLastMessageAt(Date.now());
        let payload: RunStreamMessage;
        try {
          payload = JSON.parse(event.data) as RunStreamMessage;
        } catch {
          setError("Received invalid live stream payload.");
          return;
        }
        if (payload.type === "ping") {
          socket.send(JSON.stringify({ type: "pong" }));
          return;
        }
        if (payload.type === "replay_start" || payload.type === "replay_end") {
          return;
        }
        setMessages((current) => [...current.slice(-250), payload]);
        applyPayload(payload);
      };
      socket.onclose = () => {
        setConnected(false);
        if (cancelled) {
          setPhase("closed");
          return;
        }
        const delay = Math.min(30_000, 1000 * 2 ** retryRef.current);
        setRetryCount(retryRef.current);
        setRetryDelay(delay);
        retryRef.current += 1;
        setPhase("reconnecting");
        timer = setTimeout(connect, delay);
      };
      socket.onerror = () => {
        setError("Live stream connection failed.");
        setPhase("error");
        socket.close();
      };
    };

    const applyPayload = (payload: RunStreamMessage) => {
      if (payload.type === "frame" && payload.frame_b64) {
        if (payload.frame_b64 === lastFrameRef.current) return;
        lastFrameRef.current = payload.frame_b64;
        setFrame(`data:${payload.mime_type ?? "image/jpeg"};base64,${payload.frame_b64}`);
      }
      if (payload.type === "state") {
        setState(payload);
      }
      if (payload.type === "llm_start") {
        setDecisions((current) => mergeDecision(current, {
          sequenceNumber: payload.sequence_number ?? current.length,
          tick: payload.tick,
        }));
      }
      if (payload.type === "llm_decision") {
        setVisitedCells(payload.visited_cells ?? {});
        setVisitedCellSize(payload.visited_cell_size ?? 256);
        setDecisions((current) => mergeDecision(current, {
          sequenceNumber: payload.sequence_number ?? current.length,
          tick: payload.tick,
          reasoning: payload.reasoning_summary,
          tool: payload.mcp_tool,
          params: payload.mcp_params,
          llmInput: payload.llm_input,
          llmOutput: payload.llm_raw_output,
          llmDurationMs: payload.llm_duration_ms,
          llmInputTokens: payload.llm_input_tokens ?? 0,
          llmOutputTokens: payload.llm_output_tokens ?? 0,
          llmCostEstimateUsd: payload.llm_cost_estimate_usd ?? 0,
          decisionSource: payload.decision_source,
        }));
      }
      if (payload.type === "mcp_call_start") {
        setDecisions((current) => mergeDecision(current, {
          sequenceNumber: payload.sequence_number ?? current.length,
          tick: payload.tick,
          tool: payload.mcp_tool,
          params: payload.mcp_params,
        }));
      }
      if (payload.type === "mcp_call_result") {
        setDecisions((current) => mergeDecision(current, {
          sequenceNumber: payload.sequence_number ?? current.length,
          tick: payload.tick,
          tool: payload.mcp_tool,
          params: payload.mcp_input,
          mcpOutput: payload.mcp_output,
          stopReason: payload.mcp_stop_reason,
          mcpDurationMs: payload.mcp_duration_ms,
          decisionSource: payload.decision_source,
          validationRejection: payload.validation_rejection,
        }));
      }
      if (payload.type === "progress") {
        if (payload.same_run_memory) {
          setSameRunMemory(payload.same_run_memory);
        }
      }
      if (payload.type === "defect") {
        setDefects((current) => mergeDefect(current, {
          defect_type: payload.defect_type ?? "defect",
          title: payload.title ?? payload.defect_type ?? "Defect",
          severity: payload.severity ?? 3,
          detected_at_tick: payload.detected_at_tick,
          fingerprint: payload.fingerprint,
        }));
      }
    };

    connect();
    return () => {
      cancelled = true;
      if (timer) {
        clearTimeout(timer);
      }
      socketRef.current?.close();
    };
  }, [runId]);

  const tokenTotals = useMemo(() => tokenTotalsFromDecisions(decisions), [decisions]);

  return useMemo(
    () => ({
      connected,
      retryCount,
      retryDelay,
      lastMessageAt,
      messages,
      frame,
      state,
      decisions,
      defects,
      tokenTotals,
      sameRunMemory,
      visitedCells,
      visitedCellSize,
      snapshot,
      phase,
      error,
    }),
    [connected, retryCount, retryDelay, lastMessageAt, messages, frame, state, decisions, defects, tokenTotals, sameRunMemory, visitedCells, visitedCellSize, snapshot, phase, error],
  );
}

function mergeDecision(current: LiveDecision[], next: LiveDecision): LiveDecision[] {
  const sequenceNumber = next.sequenceNumber;
  const index = current.findIndex((item) => item.sequenceNumber === sequenceNumber);
  if (index === -1) {
    return [...current, next].sort((a, b) => a.sequenceNumber - b.sequenceNumber).slice(-500);
  }
  const copy = [...current];
  copy[index] = { ...copy[index], ...definedFields(next) };
  return copy.sort((a, b) => a.sequenceNumber - b.sequenceNumber).slice(-500);
}

function mergeDefect(current: Defect[], next: Defect): Defect[] {
  const key = next.fingerprint ?? `${next.defect_type}:${next.title}:${next.detected_at_tick ?? ""}`;
  const index = current.findIndex((item) => (item.fingerprint ?? `${item.defect_type}:${item.title}:${item.detected_at_tick ?? ""}`) === key);
  if (index === -1) {
    return [...current, next].slice(-200);
  }
  const copy = [...current];
  copy[index] = { ...copy[index], ...next };
  return copy;
}

function definedFields<T extends object>(value: T): Partial<T> {
  return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined)) as Partial<T>;
}

function tokenTotalsFromDecisions(decisions: LiveDecision[]): SessionTokenTotals {
  if (!decisions.length) {
    return EMPTY_TOTALS;
  }
  return decisions.reduce(
    (total, decision) => {
      const prompt = decision.llmInputTokens ?? 0;
      const completion = decision.llmOutputTokens ?? 0;
      const cost = decision.llmCostEstimateUsd ?? 0;
      const hasUsage = prompt > 0 || completion > 0 || cost > 0;
      return {
        totalPrompt: total.totalPrompt + prompt,
        totalCompletion: total.totalCompletion + completion,
        totalTokens: total.totalTokens + prompt + completion,
        totalCost: total.totalCost + cost,
        decisionCount: total.decisionCount + (hasUsage ? 1 : 0),
      };
    },
    { ...EMPTY_TOTALS },
  );
}

function decisionFromSnapshot(decision: Decision): LiveDecision {
  return {
    sequenceNumber: decision.sequence_number,
    tick: decision.tick_after ?? decision.tick_before ?? undefined,
    reasoning: decision.reasoning_summary ?? undefined,
    tool: decision.mcp_tool ?? undefined,
    params: decision.mcp_input ?? undefined,
    mcpOutput: decision.mcp_output ?? undefined,
    stopReason: decision.mcp_stop_reason ?? undefined,
    llmDurationMs: decision.llm_duration_ms ?? undefined,
    mcpDurationMs: decision.mcp_duration_ms ?? undefined,
    llmInputTokens: decision.llm_input_tokens ?? 0,
    llmOutputTokens: decision.llm_output_tokens ?? 0,
    llmCostEstimateUsd: decision.llm_cost_estimate_usd ?? 0,
    decisionSource: decision.decision_source,
    validationRejection: decision.validation_rejection ?? undefined,
  };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Failed to load live run snapshot.";
}
