import { Decision } from "@/lib/api";

export function DecisionTimeline({ decisions }: { decisions: Decision[] }) {
  return (
    <div className="max-h-[540px] overflow-y-auto rounded border border-neutral-200 bg-white">
      {decisions.map((decision) => (
        <details key={decision.id} className="border-b border-neutral-200 p-3 last:border-b-0">
          <summary className="cursor-pointer list-none">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-semibold text-neutral-950">
                #{decision.sequence_number} {decision.mcp_tool ?? "pending"}
              </span>
              <span className="text-xs text-neutral-500">
                {decision.tick_before ?? "-"} to {decision.tick_after ?? "-"} · {decision.mcp_stop_reason ?? decision.status}
              </span>
            </div>
          </summary>
          <p className="mt-3 text-sm leading-6 text-neutral-700">{decision.reasoning_summary ?? "No reasoning stored."}</p>
        </details>
      ))}
    </div>
  );
}
