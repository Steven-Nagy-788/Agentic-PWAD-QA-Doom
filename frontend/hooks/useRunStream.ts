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
};

export type LiveDecision = {
  sequenceNumber: number;
  tick?: number;
  reasoning?: string;
  tool?: string;
  stopReason?: string;
  params?: Record<string, unknown>;
};

export function useRunStream(runId?: string) {
  const [messages, setMessages] = useState<RunStreamMessage[]>([]);
  const [frame, setFrame] = useState<string | null>(null);
  const [state, setState] = useState<RunStreamMessage | null>(null);
  const [decisions, setDecisions] = useState<LiveDecision[]>([]);
  const [defects, setDefects] = useState<Defect[]>([]);
  const [connected, setConnected] = useState(false);
  const retryRef = useRef(0);
  const socketRef = useRef<WebSocket | null>(null);

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
        setConnected(true);
      };
      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data) as RunStreamMessage;
        setMessages((current) => [...current.slice(-250), payload]);
        if (payload.type === "frame" && payload.frame_b64) {
          setFrame(`data:${payload.mime_type ?? "image/jpeg"};base64,${payload.frame_b64}`);
        }
        if (payload.type === "state") {
          setState(payload);
        }
        if (payload.type === "llm_decision") {
          setDecisions((current) => [
            ...current,
            {
              sequenceNumber: payload.sequence_number ?? current.length,
              tick: payload.tick,
              reasoning: payload.reasoning_summary,
              tool: payload.mcp_tool,
              params: payload.mcp_params,
            },
          ]);
        }
        if (payload.type === "mcp_call_result") {
          setDecisions((current) =>
            current.map((decision) =>
              decision.sequenceNumber === payload.sequence_number
                ? { ...decision, stopReason: payload.mcp_stop_reason }
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
          ]);
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (cancelled) {
          return;
        }
        const delay = Math.min(30_000, 1000 * 2 ** retryRef.current);
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
    () => ({ connected, messages, frame, state, decisions, defects }),
    [connected, messages, frame, state, decisions, defects],
  );
}
