"use client";

import { useEffect, useRef } from "react";
import { LiveDecision } from "@/hooks/useRunStream";

export function ReasoningLog({ decisions, live = false }: { decisions: LiveDecision[]; live?: boolean }) {
  const endRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (live) {
      endRef.current?.scrollIntoView({ block: "end" });
    }
  }, [decisions.length, live]);

  return (
    <div className="h-full overflow-y-auto border-l border-neutral-200 bg-white">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-neutral-200 bg-white px-4 py-3">
        <h2 className="text-sm font-semibold text-neutral-950">Reasoning</h2>
        <span className="text-xs text-neutral-500">{decisions.length}</span>
      </div>
      <div className="space-y-2 p-3">
        {decisions.map((decision) => (
          <article key={decision.sequenceNumber} className="rounded border border-neutral-200 bg-neutral-50 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-neutral-950">#{decision.sequenceNumber}</span>
              <span className="rounded border border-neutral-200 bg-white px-2 py-0.5 text-[11px] text-neutral-700">
                {decision.tool ?? "pending"} {decision.tick !== undefined ? `@ ${decision.tick}` : ""}
              </span>
            </div>
            <p className="text-sm leading-5 text-neutral-800">{decision.reasoning ?? "..."}</p>
            {decision.stopReason ? <p className="mt-2 text-xs text-neutral-500">{decision.stopReason}</p> : null}
          </article>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
