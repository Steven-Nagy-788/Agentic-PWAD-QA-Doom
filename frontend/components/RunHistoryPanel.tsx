"use client";

import { useState } from "react";
import type React from "react";
import { RunHistory } from "@/hooks/useRunStream";
import { Crosshair, Navigation, Swords, Wrench, Lightbulb, Bug, Flag, PiggyBank, Target } from "lucide-react";

function CollapsibleSection({
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
    <div className="rounded border border-neutral-200 bg-white p-2.5">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 text-left">
        <span className="text-neutral-400 [&>svg]:h-3.5 [&>svg]:w-3.5">{icon}</span>
        <span className="text-xs font-semibold text-neutral-700">{label}</span>
        {count !== undefined && <span className="ml-auto text-[11px] text-neutral-400">{count}</span>}
        <span className="text-[10px] text-neutral-400">{open ? "▲" : "▼"}</span>
      </button>
      {open && <div className="mt-2 space-y-1.5 text-xs text-neutral-700">{children}</div>}
    </div>
  );
}

function ProgressBar({ used, total }: { used: number; total: number }) {
  const pct = total > 0 ? Math.min(100, Math.round((used / total) * 100)) : 0;
  const hue = pct > 80 ? "bg-red-500" : pct > 50 ? "bg-yellow-500" : "bg-emerald-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-neutral-200">
        <div className={`h-full rounded-full ${hue}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-10 text-right text-[10px] text-neutral-500">{pct}%</span>
    </div>
  );
}

export function RunHistoryPanel({ history }: { history: RunHistory | null }) {
  if (!history) {
    return (
      <div className="h-full overflow-y-auto border-l border-neutral-200 bg-white">
        <div className="sticky top-0 z-10 border-b border-neutral-200 bg-white px-4 py-3">
          <h2 className="text-sm font-semibold text-neutral-950">Memory</h2>
        </div>
        <div className="grid h-32 place-items-center text-xs text-neutral-400">Waiting for run data</div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto border-l border-neutral-200 bg-neutral-50">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-neutral-200 bg-white px-4 py-3">
        <h2 className="text-sm font-semibold text-neutral-950">Memory</h2>
        <span className="text-xs text-neutral-500">{history.budget.decisions_made} decisions</span>
      </div>
      <div className="space-y-2 p-3">
        <CollapsibleSection icon={<Target />} label="Objective" defaultOpen>
          <div className="rounded bg-neutral-100 px-2 py-1 font-medium text-neutral-800">{history.current_objective.current}</div>
          {history.current_objective.history.length > 1 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {history.current_objective.history.map((obj, i) => (
                <span key={i} className="rounded bg-neutral-200 px-1.5 py-0.5 text-[10px] text-neutral-600">{obj}</span>
              ))}
            </div>
          )}
        </CollapsibleSection>

        <CollapsibleSection icon={<PiggyBank />} label="Budget" defaultOpen>
          <div className="grid grid-cols-3 gap-1.5">
            <div className="rounded bg-neutral-100 p-1.5 text-center">
              <div className="text-[10px] text-neutral-500">Used</div>
              <div className="font-semibold">{history.budget.ticks_used}</div>
            </div>
            <div className="rounded bg-neutral-100 p-1.5 text-center">
              <div className="text-[10px] text-neutral-500">Remaining</div>
              <div className="font-semibold">{history.budget.ticks_remaining}</div>
            </div>
            <div className="rounded bg-neutral-100 p-1.5 text-center">
              <div className="text-[10px] text-neutral-500">Avg/Tick</div>
              <div className="font-semibold">{history.budget.avg_ticks_per_decision}</div>
            </div>
          </div>
          <div className="mt-1.5">
            <div className="flex justify-between text-[10px] text-neutral-500">
              <span>Budget</span>
              <span>{history.budget.total_ticks} total ticks</span>
            </div>
            <ProgressBar used={history.budget.ticks_used} total={history.budget.total_ticks} />
          </div>
        </CollapsibleSection>

        <CollapsibleSection icon={<Wrench />} label="Tool Usage" count={Object.keys(history.tool_stats).length}>
          <div className="space-y-1">
            {Object.entries(history.tool_stats).map(([tool, stats]) => {
              const failPct = stats.total > 0 ? Math.round(((stats.blocked + stats.timeout) / stats.total) * 100) : 0;
              return (
                <div key={tool} className="flex items-center justify-between rounded bg-neutral-100 px-2 py-1">
                  <span className="font-medium text-neutral-700">{tool}</span>
                  <div className="flex items-center gap-2 text-[10px] text-neutral-500">
                    <span>{stats.total}x</span>
                    <span className={failPct > 50 ? "text-red-600 font-semibold" : "text-amber-600"}>{failPct}% fail</span>
                  </div>
                </div>
              );
            })}
          </div>
        </CollapsibleSection>

        <CollapsibleSection icon={<Swords />} label="Combat" count={history.combat.total_engagements}>
          <div className="grid grid-cols-2 gap-1.5">
            <div className="rounded bg-neutral-100 p-1.5 text-center">
              <div className="text-[10px] text-neutral-500">Kills</div>
              <div className="font-semibold">{history.combat.total_kills}</div>
            </div>
            <div className="rounded bg-neutral-100 p-1.5 text-center">
              <div className="text-[10px] text-neutral-500">Engagements</div>
              <div className="font-semibold">{history.combat.total_engagements}</div>
            </div>
          </div>
          {Object.keys(history.combat.weapon_performance).length > 0 && (
            <div className="mt-1">
              <div className="text-[10px] font-medium text-neutral-500 mb-1">Weapons</div>
              {Object.entries(history.combat.weapon_performance).map(([weapon, perf]) => (
                <div key={weapon} className="flex items-center justify-between rounded bg-neutral-100 px-2 py-0.5 text-[11px]">
                  <span>{weapon}</span>
                  <span className="text-neutral-500">{perf.kills}k/{perf.shots}s ({Math.round(perf.accuracy * 100)}%)</span>
                </div>
              ))}
            </div>
          )}
        </CollapsibleSection>

        <CollapsibleSection icon={<Bug />} label="Defects" count={history.defects.length}>
          {history.defects.length === 0 ? (
            <div className="text-[11px] text-neutral-400 italic">No defects detected</div>
          ) : (
            history.defects.map((def, i) => (
              <div key={def.fingerprint ?? i} className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px]">
                <div className="flex items-center justify-between font-medium text-amber-900">
                  {def.title}
                  <span className="text-amber-700">S{def.severity}</span>
                </div>
              </div>
            ))
          )}
        </CollapsibleSection>

        <CollapsibleSection icon={<Flag />} label="Checkpoints" count={history.checkpoints.length}>
          {history.checkpoints.length === 0 ? (
            <div className="text-[11px] text-neutral-400 italic">None reached</div>
          ) : (
            history.checkpoints.map((cp, i) => (
              <div key={i} className="flex items-center justify-between rounded bg-neutral-100 px-2 py-0.5 text-[11px]">
                <span className="truncate">{cp.event}</span>
                <span className="text-neutral-400 ml-2">@{cp.tick}</span>
              </div>
            ))
          )}
        </CollapsibleSection>

        <CollapsibleSection icon={<Lightbulb />} label="Hypotheses" count={history.hypotheses.length}>
          {history.hypotheses.length === 0 ? (
            <div className="text-[11px] text-neutral-400 italic">None</div>
          ) : (
            history.hypotheses.map((h, i) => (
              <div key={i} className="rounded bg-neutral-100 px-2 py-1 text-[11px] leading-4">{h}</div>
            ))
          )}
        </CollapsibleSection>

        <CollapsibleSection icon={<Crosshair />} label="Decisions" count={history.decisions.length}>
          {history.decisions.slice(-10).reverse().map((d) => (
            <div key={d.seq} className="rounded border border-neutral-200 bg-white p-1.5 text-[11px] leading-4">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-neutral-800">#{d.seq} {d.tool}</span>
                <span className={`text-[10px] ${d.result === "success" ? "text-emerald-600" : d.result === "blocked" ? "text-amber-600" : "text-red-600"}`}>
                  {d.result}
                </span>
              </div>
              <div className="text-neutral-500 truncate">{d.key_findings}</div>
            </div>
          ))}
        </CollapsibleSection>

        <CollapsibleSection icon={<Navigation />} label="Recent Events" count={history.events.length}>
          {history.events.slice(-10).reverse().map((e, i) => (
            <div key={i} className="flex items-center justify-between rounded bg-neutral-100 px-2 py-0.5 text-[11px]">
              <div className="flex items-center gap-1.5">
                <span className="text-neutral-400">@{e.tick}</span>
                <span>{e.type}</span>
              </div>
              <span className="text-neutral-500 truncate">{e.detail}</span>
            </div>
          ))}
        </CollapsibleSection>
      </div>
    </div>
  );
}
