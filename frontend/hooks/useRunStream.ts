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
  mcp_duration_ms?: number;
  guard_status?: string;
  llm_input_tokens?: number;
  llm_output_tokens?: number;
  llm_cost_estimate_usd?: number;
  run_history?: RunHistory;
};

export type RunHistory = {
  decisions: RunHistoryDecision[];
  events: RunHistoryEvent[];
  position_trail: { tick: number; x: number; y: number; angle: number }[];
  combat: RunHistoryCombat;
  tool_stats: Record<string, { total: number; success: number; timeout: number; blocked: number }>;
  hypotheses: string[];
  defects: { defect_type: string; title: string; severity: number; fingerprint?: string | null }[];
  checkpoints: { tick: number; event: string; pos: { x: number; y: number } }[];
  budget: {
    total_ticks: number;
    ticks_used: number;
    ticks_remaining: number;
    decisions_made: number;
    avg_ticks_per_decision: number;
    estimated_decisions_remaining: number;
  };
  current_objective: { current: string; history: string[] };
};

export type RunHistoryDecision = {
  seq: number;
  tick_before: number;
  tick_after: number;
  tool: string;
  stop_reason: string;
  result: string;
  params: Record<string, unknown>;
  key_findings: string;
  reasoning: string;
  guard_modified: boolean;
  llm_ms: number;
  mcp_ms: number;
};

export type RunHistoryEvent = {
  tick: number;
  type: string;
  detail: string;
  pos: { x: number; y: number };
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
  guardStatus?: "kept" | "modified" | "blocked";
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
  run_history: RunHistory | null;
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
  const [runHistory, setRunHistory] = useState<RunHistory | null>(null);
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
        setRunHistory(data.run_history ?? null);
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
          guardStatus: normalizeGuardStatus(payload.guard_status),
        }));
      }
      if (payload.type === "progress") {
        if (payload.run_history) {
          setRunHistory(payload.run_history);
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
      runHistory,
      snapshot,
      phase,
      error,
    }),
    [connected, retryCount, retryDelay, lastMessageAt, messages, frame, state, decisions, defects, tokenTotals, runHistory, snapshot, phase, error],
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
  };
}

function normalizeGuardStatus(value?: string): "kept" | "modified" | "blocked" {
  if (value === "modified" || value === "blocked") {
    return value;
  }
  return "kept";
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Failed to load live run snapshot.";
}
