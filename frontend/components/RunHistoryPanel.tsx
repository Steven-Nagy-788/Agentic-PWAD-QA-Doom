"use client";

import { useState } from "react";
import type React from "react";
import { ChevronDown, ChevronRight, Clock3, History, ListChecks, TriangleAlert } from "lucide-react";
import type { SameRunMemory } from "@/hooks/useRunStream";

function Section({
  icon,
  label,
  count,
  defaultOpen = false,
  children,
}: {
  icon: React.ReactElement;
  label: string;
  count?: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="border-b border-neutral-200 bg-white">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-left">
        <span className="text-neutral-400 [&>svg]:h-3.5 [&>svg]:w-3.5">{icon}</span>
        <span className="text-xs font-semibold text-neutral-700">{label}</span>
        {count !== undefined ? <span className="ml-auto text-[11px] text-neutral-400">{count}</span> : null}
        {open ? <ChevronDown className="h-3.5 w-3.5 text-neutral-400" /> : <ChevronRight className="h-3.5 w-3.5 text-neutral-400" />}
      </button>
      {open ? <div className="space-y-1.5 px-3 pb-3 text-xs text-neutral-700">{children}</div> : null}
    </section>
  );
}

export function RunHistoryPanel({ memory }: { memory: SameRunMemory | null }) {
  if (!memory) {
    return <div className="grid h-32 place-items-center text-xs text-neutral-400">Waiting for same-run ledger</div>;
  }
  const milestones = memory.older_milestones;
  const aggregates = memory.aggregates;

  return (
    <div className="h-full overflow-y-auto bg-neutral-50">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-neutral-200 bg-white px-3 py-2">
        <h2 className="text-sm font-semibold text-neutral-950">Same-Run Ledger</h2>
        <span className="text-xs text-neutral-500">{aggregates.total_actions} actions</span>
      </div>
      <Section icon={<Clock3 />} label="Budget" defaultOpen>
        <div className="grid grid-cols-3 gap-1.5">
          <RunMetric label="Used" value={memory.budget.ticks_used} />
          <RunMetric label="Remaining" value={memory.budget.ticks_remaining} />
          <RunMetric label="Avg/action" value={memory.budget.avg_ticks_per_decision} />
        </div>
      </Section>
      <Section icon={<ListChecks />} label="Recent Actions" count={memory.recent_actions.length} defaultOpen>
        {memory.recent_actions.slice().reverse().map((action) => (
          <div key={action.seq} className="rounded border border-neutral-200 bg-neutral-50 px-2 py-1.5">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-neutral-800">#{action.seq} {action.tool}</span>
              <span className="text-[10px] text-neutral-500">{action.stop_reason}</span>
            </div>
            <p className="mt-1 text-[11px] leading-4 text-neutral-600">{action.reasoning}</p>
            <p className="mt-1 text-[10px] text-neutral-400">{action.decision_source} · tics {action.tick_before} to {action.tick_after}</p>
            {action.validation_rejection ? <p className="mt-1 text-[11px] text-red-700">{action.validation_rejection}</p> : null}
          </div>
        ))}
      </Section>
      <Section icon={<History />} label="Older Milestones" count={milestones.compacted_action_count}>
        <KeyValues values={milestones.tool_counts} empty="No compacted actions yet" />
        {milestones.checkpoints.map((checkpoint, index) => (
          <p key={`${checkpoint.tick}-${index}`} className="text-[11px] text-neutral-600">
            Tick {checkpoint.tick}: {checkpoint.event}
          </p>
        ))}
        {milestones.hypotheses.map((hypothesis, index) => (
          <p key={index} className="text-[11px] leading-4 text-neutral-600">{hypothesis}</p>
        ))}
      </Section>
      <Section icon={<TriangleAlert />} label="Runtime Warnings" count={aggregates.runtime_warnings.length}>
        {aggregates.runtime_warnings.length ? aggregates.runtime_warnings.map((warning, index) => (
          <p key={index} className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-900">{warning}</p>
        )) : <p className="text-[11px] text-neutral-400">No runtime warnings</p>}
      </Section>
    </div>
  );
}

function RunMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded bg-neutral-100 p-1.5 text-center">
      <div className="text-[10px] text-neutral-500">{label}</div>
      <div className="font-semibold">{value}</div>
    </div>
  );
}

function KeyValues({ values, empty }: { values: Record<string, number>; empty: string }) {
  const entries = Object.entries(values);
  if (!entries.length) return <p className="text-[11px] text-neutral-400">{empty}</p>;
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([label, value]) => <span key={label} className="rounded bg-neutral-100 px-1.5 py-0.5 text-[11px]">{label}: {value}</span>)}
    </div>
  );
}
