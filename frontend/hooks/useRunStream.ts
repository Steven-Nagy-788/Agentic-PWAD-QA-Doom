"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Defect, websocketUrl } from "@/lib/api";

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
  const [tokenTotals, setTokenTotals] = useState<SessionTokenTotals>({ totalPrompt: 0, totalCompletion: 0, totalTokens: 0, totalCost: 0, decisionCount: 0 });
  const retryRef = useRef(0);
  const socketRef = useRef<WebSocket | null>(null);
  const lastFrameRef = useRef("");

  useEffect(() => {
    if (!runId) {
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const socket = new WebSocket(websocketUrl(runId));
      socketRef.current = socket;
      socket.onopen = () => {
        retryRef.current = 0;
        setRetryCount(0);
        setRetryDelay(0);
        setConnected(true);
      };
      socket.onmessage = (event) => {
        setLastMessageAt(Date.now());
        const payload = JSON.parse(event.data) as RunStreamMessage;
        if (payload.type === "ping") {
          socket.send(JSON.stringify({ type: "pong" }));
          return;
        }
        setMessages((current) => [...current.slice(-250), payload]);
        if (payload.type === "frame" && payload.frame_b64) {
          if (payload.frame_b64 === lastFrameRef.current) return;
          lastFrameRef.current = payload.frame_b64;
          setFrame(`data:${payload.mime_type ?? "image/jpeg"};base64,${payload.frame_b64}`);
        }
        if (payload.type === "state") {
          setState(payload);
        }
        if (payload.type === "llm_decision") {
          const inputTokens = payload.llm_input_tokens ?? 0;
          const outputTokens = payload.llm_output_tokens ?? 0;
          const cost = payload.llm_cost_estimate_usd ?? 0;
          setTokenTotals((current) => ({
            totalPrompt: current.totalPrompt + inputTokens,
            totalCompletion: current.totalCompletion + outputTokens,
            totalTokens: current.totalTokens + inputTokens + outputTokens,
            totalCost: current.totalCost + cost,
            decisionCount: current.decisionCount + 1,
          }));
          setDecisions((current) => [
            ...current,
            {
              sequenceNumber: payload.sequence_number ?? current.length,
              tick: payload.tick,
              reasoning: payload.reasoning_summary,
              tool: payload.mcp_tool,
              params: payload.mcp_params,
              llmInput: payload.llm_input,
              llmOutput: payload.llm_raw_output,
              llmDurationMs: payload.llm_duration_ms,
              llmInputTokens: inputTokens,
              llmOutputTokens: outputTokens,
              llmCostEstimateUsd: cost,
            },
          ].slice(-500));
        }
        if (payload.type === "mcp_call_result") {
          setDecisions((current) =>
            current.map((decision) =>
              decision.sequenceNumber === payload.sequence_number
                ? {
                    ...decision,
                    params: payload.mcp_input ?? decision.params,
                    mcpOutput: payload.mcp_output,
                    stopReason: payload.mcp_stop_reason,
                    mcpDurationMs: payload.mcp_duration_ms,
                    guardStatus: (payload.guard_status ?? "kept") as "kept" | "modified" | "blocked",
                  }
                : decision,
            ),
          );
        }
        if (payload.type === "defect") {
          setDefects((current) => [
            ...current,
            {
              defect_type: payload.defect_type ?? "defect",
              title: payload.title ?? payload.defect_type ?? "Defect",
              severity: payload.severity ?? 3,
              detected_at_tick: payload.detected_at_tick,
              fingerprint: payload.fingerprint,
            },
          ].slice(-200));
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (cancelled) {
          return;
        }
        const delay = Math.min(30_000, 1000 * 2 ** retryRef.current);
        setRetryCount(retryRef.current);
        setRetryDelay(delay);
        retryRef.current += 1;
        timer = setTimeout(connect, delay);
      };
      socket.onerror = () => socket.close();
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

  return useMemo(
    () => ({ connected, retryCount, retryDelay, lastMessageAt, messages, frame, state, decisions, defects, tokenTotals }),
    [connected, retryCount, retryDelay, lastMessageAt, messages, frame, state, decisions, defects, tokenTotals],
  );
}
