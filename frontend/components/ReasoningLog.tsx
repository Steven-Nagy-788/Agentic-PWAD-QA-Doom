"use client";

import { useState } from "react";
import { LiveDecision } from "@/hooks/useRunStream";

function GuardBadge({ status }: { status?: "kept" | "modified" | "blocked" }) {
  if (!status) return null;
  const colors: Record<string, string> = {
    kept: "bg-green-100 text-green-800 border-green-300",
    modified: "bg-yellow-100 text-yellow-800 border-yellow-300",
    blocked: "bg-red-100 text-red-800 border-red-300",
  };
  return (
    <span className={`rounded border px-2 py-0.5 text-[11px] font-medium ${colors[status] ?? "bg-neutral-100 text-neutral-600 border-neutral-200"}`}>
      {status}
    </span>
  );
}

function DecisionCard({ decision, defaultExpanded = false }: { decision: LiveDecision; defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <article className="min-w-0 overflow-hidden rounded border border-neutral-200 bg-neutral-50 p-3">
      <div className="mb-2 flex min-w-0 items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-xs font-semibold text-neutral-950">#{decision.sequenceNumber}</span>
          <GuardBadge status={decision.guardStatus} />
        </div>
        <span className="shrink-0 rounded border border-neutral-200 bg-white px-2 py-0.5 text-[11px] text-neutral-700">
          {decision.tool ?? "pending"} {decision.tick !== undefined ? `@ ${decision.tick}` : ""}
        </span>
      </div>
      <p className="break-words text-sm leading-5 text-neutral-800 [overflow-wrap:anywhere]">{decision.reasoning ?? "..."}</p>

      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-2 text-xs text-blue-600 hover:text-blue-800 focus:outline-none"
      >
        {expanded ? "Hide details" : "Show details"}
      </button>

      {expanded && (
        <div className="mt-2 space-y-2 border-t border-neutral-200 pt-2 text-xs text-neutral-700">
          {decision.llmDurationMs !== undefined && (
            <div className="flex justify-between">
              <span className="font-medium">LLM latency</span>
              <span>{decision.llmDurationMs.toFixed(1)} ms</span>
            </div>
          )}
          {decision.mcpDurationMs !== undefined && (
            <div className="flex justify-between">
              <span className="font-medium">MCP latency</span>
              <span>{decision.mcpDurationMs.toFixed(1)} ms</span>
            </div>
          )}
          {decision.llmInputTokens !== undefined && (
            <div className="flex justify-between">
              <span className="font-medium">Input tokens</span>
              <span>{decision.llmInputTokens}</span>
            </div>
          )}
          {decision.llmOutputTokens !== undefined && (
            <div className="flex justify-between">
              <span className="font-medium">Output tokens</span>
              <span>{decision.llmOutputTokens}</span>
            </div>
          )}
          {decision.llmCostEstimateUsd !== undefined && (
            <div className="flex justify-between">
              <span className="font-medium">Cost (USD)</span>
              <span>${decision.llmCostEstimateUsd.toFixed(8)}</span>
            </div>
          )}
          {decision.stopReason && (
            <div>
              <span className="font-medium">Stop reason: </span>
              <span className="text-neutral-600">{decision.stopReason}</span>
            </div>
          )}
          {decision.params && Object.keys(decision.params).length > 0 && (
            <div>
              <span className="mb-0.5 block font-medium">MCP input</span>
              <pre className="overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-100 p-2 text-[10px] leading-4 [overflow-wrap:anywhere]">
                {JSON.stringify(decision.params, null, 2)}
              </pre>
            </div>
          )}
          {decision.mcpOutput && Object.keys(decision.mcpOutput).length > 0 && (
            <div>
              <span className="mb-0.5 block font-medium">MCP output</span>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-100 p-2 text-[10px] leading-4 [overflow-wrap:anywhere]">
                {JSON.stringify(decision.mcpOutput, null, 2)}
              </pre>
            </div>
          )}
          {decision.llmInput && Object.keys(decision.llmInput).length > 0 && (
            <div>
              <span className="mb-0.5 block font-medium">LLM input</span>
              <pre className="overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-100 p-2 text-[10px] leading-4 [overflow-wrap:anywhere]">
                {JSON.stringify(decision.llmInput, null, 2)}
              </pre>
            </div>
          )}
          {decision.llmOutput && Object.keys(decision.llmOutput).length > 0 && (
            <div>
              <span className="mb-0.5 block font-medium">Raw LLM output</span>
              <pre className="overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-100 p-2 text-[10px] leading-4 [overflow-wrap:anywhere]">
                {JSON.stringify(decision.llmOutput, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export function ReasoningLog({ decisions, live = false }: { decisions: LiveDecision[]; live?: boolean }) {
  const visibleDecisions = live ? decisions.slice(-30) : decisions;

  return (
    <div className="h-full overflow-y-auto border-l border-neutral-200 bg-white">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-neutral-200 bg-white px-4 py-3">
        <h2 className="text-sm font-semibold text-neutral-950">Reasoning</h2>
        <span className="text-xs text-neutral-500">
          {visibleDecisions.length}
          {visibleDecisions.length < decisions.length ? `/${decisions.length}` : ""}
        </span>
      </div>
      <div className="space-y-2 p-3">
        {visibleDecisions.map((decision) => (
          <DecisionCard key={decision.sequenceNumber} decision={decision} defaultExpanded={false} />
        ))}
      </div>
    </div>
  );
}
