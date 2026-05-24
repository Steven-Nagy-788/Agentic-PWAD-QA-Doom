import { Decision } from "@/lib/api";

export function DecisionTimeline({ decisions }: { decisions: Decision[] }) {
  return (
    <div className="max-h-[540px] overflow-y-auto rounded border border-neutral-200 bg-white" role="list" aria-label="Decision trace timeline">
      {decisions.map((decision) => (
        <details key={decision.id} className="border-b border-neutral-200 p-3 last:border-b-0" role="listitem">
          <summary className="cursor-pointer list-none">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-semibold text-neutral-950">
                #{decision.sequence_number} {decision.mcp_tool ?? "pending"}
              </span>
              <span className="text-xs text-neutral-500">
                {decision.tick_before ?? "-"} to {decision.tick_after ?? "-"} · {decision.mcp_stop_reason ?? decision.status}
              </span>
            </div>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-neutral-400">
              {decision.llm_duration_ms != null ? <span>LLM {decision.llm_duration_ms.toFixed(0)}ms</span> : null}
              {decision.mcp_duration_ms != null ? <span>MCP {decision.mcp_duration_ms.toFixed(0)}ms</span> : null}
              {decision.llm_input_tokens != null ? <span>{decision.llm_input_tokens}→{decision.llm_output_tokens ?? "?"}tok</span> : null}
              {decision.llm_cost_estimate_usd != null ? <span>${decision.llm_cost_estimate_usd.toFixed(8)}</span> : null}
            </div>
          </summary>
          <div className="mt-3 space-y-2">
            <p className="text-sm leading-6 text-neutral-700">{decision.reasoning_summary ?? "No reasoning stored."}</p>
            <div className="grid grid-cols-3 gap-2 text-xs text-neutral-600">
              {decision.llm_duration_ms != null ? (
                <span>LLM: {decision.llm_duration_ms.toFixed(1)}ms</span>
              ) : null}
              {decision.mcp_duration_ms != null ? (
                <span>MCP: {decision.mcp_duration_ms.toFixed(1)}ms</span>
              ) : null}
              {decision.llm_input_tokens != null ? (
                <span>In: {decision.llm_input_tokens} tok</span>
              ) : null}
              {decision.llm_output_tokens != null ? (
                <span>Out: {decision.llm_output_tokens} tok</span>
              ) : null}
              {decision.llm_cost_estimate_usd != null ? (
                <span>Cost: ${decision.llm_cost_estimate_usd.toFixed(8)}</span>
              ) : null}
            </div>
            <div className="grid gap-2 text-xs lg:grid-cols-2">
              {decision.mcp_input ? (
                <div>
                  <div className="mb-1 font-semibold text-neutral-700">MCP input</div>
                  <pre className="max-h-48 overflow-auto rounded bg-neutral-50 p-2 text-[10px] leading-4 text-neutral-700">
                    {JSON.stringify(decision.mcp_input, null, 2)}
                  </pre>
                </div>
              ) : null}
              {decision.mcp_output ? (
                <div>
                  <div className="mb-1 font-semibold text-neutral-700">MCP output</div>
                  <pre className="max-h-48 overflow-auto rounded bg-neutral-50 p-2 text-[10px] leading-4 text-neutral-700">
                    {JSON.stringify(decision.mcp_output, null, 2)}
                  </pre>
                </div>
              ) : null}
            </div>
          </div>
        </details>
      ))}
    </div>
  );
}
