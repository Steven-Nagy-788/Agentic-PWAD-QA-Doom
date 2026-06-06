"use client";

/* eslint-disable @next/next/no-img-element */

import { use, useState } from "react";
import type React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Activity, X } from "lucide-react";
import { Run, Defect, Decision, PositionSample, TraceEntry, UsageStats, BenchmarkStats, WadMap, ReportStatus, apiGet, apiSend, API_BASE } from "@/lib/api";
import { useRunStream, type LiveDecision, type SameRunMemory } from "@/hooks/useRunStream";
import { Metric, OutcomeBadge, SkeletonRows, formatTime } from "@/lib/components/shared";
import { DefectBadge } from "@/components/DefectBadge";
import { DecisionTimeline } from "@/components/DecisionTimeline";
import { MapCanvas } from "@/components/MapCanvas";
import { ReasoningLog } from "@/components/ReasoningLog";
import { RunHistoryPanel } from "@/components/RunHistoryPanel";
import { StatBar } from "@/components/StatBar";

const LIVE_STATUSES = new Set(["queued", "pending", "analyzing", "running"]);

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const run = useQuery({ queryKey: ["run", id], queryFn: () => apiGet<Run>(`/runs/${id}`), refetchInterval: 8_000 });

  if (run.isLoading) return <SkeletonRows />;
  if (!run.data) return <div className="p-6 text-neutral-500">Run not found</div>;

  const isLive = LIVE_STATUSES.has(run.data.status);
  if (isLive) {
    return <LiveRunContent runId={id} initialRun={run.data} />;
  }
  return <RunDetailContent runId={id} />;
}

function LiveRunContent({ runId, initialRun }: { runId: string; initialRun: Run }) {
  const router = useRouter();
  const stream = useRunStream(runId);
  const queryClient = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => apiSend<Run>(`/runs/${runId}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      router.refresh();
    },
  });
  const tt = stream.tokenTotals;
  const run = { ...initialRun, ...(stream.snapshot?.run ?? {}) };
  const reportStatus = stream.snapshot?.report_status;
  const usage = stream.snapshot?.usage;
  const trail = liveTrail(stream.sameRunMemory, stream.snapshot?.position_trail ?? []);
  const events = stream.snapshot?.events ?? [];
  const visibleDefects = stream.defects.filter((defect) => !isCosmeticTextureDefect(defect));
  const latestDecision = stream.decisions.at(-1);
  const isTerminal = run.status === "completed" || run.status === "failed" || run.status === "cancelled";
  const maps = useQuery({
    queryKey: ["run-maps-live", run.wad_file_id],
    queryFn: () => apiGet<WadMap[]>(`/wads/${run.wad_file_id}/maps`),
    enabled: Boolean(run.wad_file_id),
  });
  const map = maps.data?.find((item) => item.map_name === run.map_name);

  const [tab, setTab] = useState<"reasoning" | "mcp" | "memory" | "defects">("reasoning");

  return (
    <div className="fixed inset-0 z-50 grid grid-rows-[auto_1fr_auto] overflow-hidden bg-neutral-100">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-200 bg-white px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-base font-semibold text-neutral-950">{map?.map_display_name || run.map_name}</h1>
            {map?.map_display_name ? <span className="text-xs text-neutral-500">{run.map_name}</span> : null}
            <OutcomeBadge outcome={run.outcome ?? run.status} />
            <ConnectionBadge connected={stream.connected} phase={stream.phase} />
          </div>
          <p className="truncate text-xs text-neutral-500">
            {run.id} · {run.behavior_profile ?? "default"} · {stream.lastMessageAt ? `last update ${formatTime(stream.lastMessageAt)}` : "waiting for stream"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <DefectBadge count={visibleDefects.length} pulse={visibleDefects.length > 0} />
          <a
            href={isTerminal ? `${API_BASE}/runs/${runId}/report/pdf` : "#"}
            aria-disabled={!isTerminal}
            className={`inline-flex h-9 items-center rounded border px-3 text-sm font-semibold ${
              isTerminal ? "border-neutral-300 bg-white text-neutral-900 hover:bg-neutral-50" : "cursor-not-allowed border-neutral-200 bg-neutral-100 text-neutral-400"
            }`}
          >
            Report
          </a>
          <button
            onClick={() => cancel.mutate()}
            disabled={cancel.isPending || isTerminal}
            className="inline-flex h-9 items-center gap-2 rounded bg-neutral-950 px-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-neutral-400"
          >
            <X className="h-4 w-4" aria-hidden="true" />
            Cancel
          </button>
        </div>
      </header>

      <main className="grid min-h-0 grid-cols-1 grid-rows-[minmax(0,1fr)_minmax(11rem,0.55fr)] gap-3 p-3 lg:grid-cols-[minmax(0,1fr)_420px] lg:grid-rows-1">
        <section className="grid min-h-0 grid-rows-[minmax(0,1fr)_auto] overflow-hidden rounded border border-neutral-200 bg-white">
          <div className="grid min-h-0 grid-cols-1 grid-rows-[minmax(0,0.75fr)_minmax(16rem,1fr)] overflow-hidden xl:grid-cols-[minmax(0,1fr)_320px] xl:grid-rows-1">
            <div className="grid min-h-0 place-items-center bg-white overflow-hidden p-2">
              {stream.frame ? (
                <img src={stream.frame} alt="Live game frame" role="img" aria-label="Live game frame" className="h-full w-full object-contain" />
              ) : (
                <div className="grid aspect-[4/3] w-full max-w-4xl place-items-center border border-neutral-200 bg-neutral-50 text-sm text-neutral-400">
                  Waiting for live frame
                </div>
              )}
            </div>
            <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden border-t border-neutral-200 bg-neutral-50 xl:border-l xl:border-t-0">
              <div className="border-b border-neutral-200 bg-white px-3 py-2">
                <h2 className="text-xs font-semibold uppercase text-neutral-500">Map And Trail</h2>
              </div>
              <div className="min-h-0 overflow-hidden p-3">
                <MapCanvas
                  map={map}
                  trail={trail}
                  events={events}
                  livePosition={stream.state?.position ?? null}
                  visitedCells={stream.visitedCells ?? {}}
                  visitedCellSize={stream.visitedCellSize}
                  fit="contain"
                  className="h-full w-full"
                />
              </div>
              <div className="grid grid-cols-3 gap-2 border-t border-neutral-200 bg-white p-3 text-xs">
                <MiniStat label="Trail" value={trail.length} />
                <MiniStat label="Events" value={events.length} />
                <MiniStat label="Tick" value={stream.state?.tick ?? 0} />
              </div>
            </div>
          </div>
          <div className="grid gap-2 border-t border-neutral-200 p-3 md:grid-cols-4">
            <Metric label="LLM Calls" value={Math.max(usage?.total_llm_calls ?? 0, tt.decisionCount)} />
            <Metric label="Prompt Tokens" value={Math.max(usage?.total_prompt_tokens ?? 0, tt.totalPrompt).toLocaleString()} />
            <Metric label="Completion" value={Math.max(usage?.total_completion_tokens ?? 0, tt.totalCompletion).toLocaleString()} />
            <Metric label="Est. Cost" value={`$${Math.max(usage?.estimated_cost_usd ?? 0, tt.totalCost).toFixed(6)}`} />
          </div>
        </section>

        <aside className="grid min-h-0 grid-rows-[auto_auto_minmax(0,1fr)] overflow-hidden rounded border border-neutral-200 bg-white">
          <div className="grid grid-cols-3 gap-2 border-b border-neutral-200 p-3">
            <MiniStat label="Status" value={run.status} />
            <MiniStat label="Report" value={reportStatus?.status ?? "pending"} />
            <MiniStat label="Defects" value={visibleDefects.length} />
          </div>
          {stream.error ? (
            <div className="border-b border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700" role="alert">
              {stream.error}
            </div>
          ) : latestDecision ? (
            <div className="border-b border-neutral-200 bg-neutral-50 px-3 py-2 text-xs text-neutral-700">
              <span className="font-semibold">Latest:</span> #{latestDecision.sequenceNumber} {latestDecision.tool ?? "pending"} {latestDecision.stopReason ? `· ${latestDecision.stopReason}` : ""}
            </div>
          ) : null}
          <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)]">
            <div className="flex border-b border-neutral-200 bg-white" role="tablist">
              <TabButton active={tab === "reasoning"} onClick={() => setTab("reasoning")} id="tab-reasoning" aria-controls="panel-reasoning">Reasoning</TabButton>
              <TabButton active={tab === "mcp"} onClick={() => setTab("mcp")} id="tab-mcp" aria-controls="panel-mcp">MCP</TabButton>
              <TabButton active={tab === "memory"} onClick={() => setTab("memory")} id="tab-memory" aria-controls="panel-memory">Memory</TabButton>
              <TabButton active={tab === "defects"} onClick={() => setTab("defects")} id="tab-defects" aria-controls="panel-defects">Defects</TabButton>
            </div>
            <div className="min-h-0 overflow-hidden" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
            {tab === "reasoning" ? (
              <ReasoningLog decisions={stream.decisions} live />
            ) : tab === "mcp" ? (
              <McpInspector decisions={stream.decisions} />
            ) : tab === "defects" ? (
              <DefectPanel defects={visibleDefects} />
            ) : (
              <RunHistoryPanel memory={stream.sameRunMemory} />
            )}
            </div>
          </div>
        </aside>
      </main>
      {stream.sameRunMemory?.aggregates?.runtime_warnings?.length ? <div className="px-3"><RuntimeWarnings flags={{ warnings: stream.sameRunMemory.aggregates.runtime_warnings }} /></div> : null}
      <StatBar state={{ ...stream.state, secrets: stream.state?.secrets }} />
    </div>
  );
}

function ConnectionBadge({ connected, phase }: { connected: boolean; phase: string }) {
  return (
    <span className={`rounded border px-2 py-0.5 text-xs font-semibold ${connected ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-700"}`}>
      {connected ? "connected" : phase}
    </span>
  );
}

function TabButton({ active, onClick, children, ...props }: { active: boolean; onClick: () => void; children: React.ReactNode } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      onClick={onClick}
      role="tab"
      aria-selected={active}
      className={`min-h-10 flex-1 border-b-2 px-2 text-center text-xs font-semibold ${
        active ? "border-neutral-950 text-neutral-950" : "border-transparent text-neutral-500 hover:text-neutral-700"
      }`}
      {...props}
    >
      {children}
    </button>
  );
}

function MiniStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-0 rounded border border-neutral-200 bg-white px-2 py-1.5">
      <div className="text-[10px] font-medium uppercase text-neutral-500">{label}</div>
      <div className="truncate text-sm font-semibold text-neutral-950">{value}</div>
    </div>
  );
}

function McpInspector({ decisions }: { decisions: LiveDecision[] }) {
  const visible = decisions.filter((decision) => decision.tool || decision.mcpOutput || decision.params).slice(-25).reverse();
  return (
    <div className="h-full overflow-y-auto bg-white p-3">
      {visible.length === 0 ? (
        <div className="grid h-32 place-items-center text-xs text-neutral-400">Waiting for MCP calls</div>
      ) : (
        <div className="space-y-2">
          {visible.map((decision) => (
            <article key={decision.sequenceNumber} className="min-w-0 overflow-hidden rounded border border-neutral-200 bg-neutral-50 p-3">
              <div className="mb-2 flex min-w-0 items-center justify-between gap-2 text-xs">
                <span className="min-w-0 truncate font-semibold text-neutral-950">#{decision.sequenceNumber} {decision.tool ?? "pending"}</span>
                <span className="shrink-0 text-neutral-500">{decision.stopReason ?? "in flight"}</span>
              </div>
              <JsonBlock label="Input" value={decision.params} />
              <JsonBlock label="Output" value={decision.mcpOutput} />
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function JsonBlock({ label, value }: { label: string; value?: Record<string, unknown> }) {
  if (!value || Object.keys(value).length === 0) return null;
  return (
    <div className="mt-2 min-w-0">
      <div className="mb-1 text-[10px] font-semibold uppercase text-neutral-500">{label}</div>
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-950 p-2 text-[10px] leading-4 text-neutral-100 [overflow-wrap:anywhere]">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

function DefectPanel({ defects }: { defects: Defect[] }) {
  return (
    <div className="h-full overflow-y-auto bg-white p-3">
      {defects.length === 0 ? (
        <div className="grid h-32 place-items-center text-xs text-neutral-400">No defects reported yet</div>
      ) : (
        <div className="space-y-2">
          {defects.map((defect, index) => (
            <article key={defect.fingerprint ?? defect.id ?? index} className="min-w-0 overflow-hidden rounded border border-amber-200 bg-amber-50 p-3">
              <div className="flex min-w-0 items-start justify-between gap-3">
                <span className="min-w-0 break-words font-semibold text-amber-950 [overflow-wrap:anywhere]">{defect.title}</span>
                <span className="shrink-0 text-xs font-semibold text-amber-800">S{defect.severity}</span>
              </div>
              {defect.description ? <p className="mt-1 break-words text-sm text-amber-900 [overflow-wrap:anywhere]">{defect.description}</p> : null}
              <p className="mt-1 break-words text-xs text-amber-700 [overflow-wrap:anywhere]">{defect.defect_type}{defect.detected_at_tick ? ` · tick ${defect.detected_at_tick}` : ""}</p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function isCosmeticTextureDefect(defect: Defect) {
  const type = (defect.defect_type ?? "").toLowerCase();
  const text = `${type} ${defect.title ?? ""} ${defect.description ?? ""}`.toLowerCase();
  if (text.includes("hom") || text.includes("hall of mirrors") || text.includes("missing texture") || text.includes("medusa")) {
    return false;
  }
  if (type === "visual_texture_misalignment") {
    return true;
  }
  const issue = ["alignment", "misalign", "offset", "tiling", "discontinuity", "repeat", "cut-off", "cut off", "seam"].some((term) => text.includes(term));
  const surface = ["texture", "floor", "wall", "pillar"].some((term) => text.includes(term));
  return issue && surface;
}

function liveTrail(memory: SameRunMemory | null, snapshotTrail: PositionSample[]): PositionSample[] {
  const positions = memory?.recent_actions
    .map((action) => ({ ...action.final_position, tick: action.tick_after }))
    .filter((sample) => sample.x !== undefined && sample.y !== undefined) ?? [];
  const latestHealth = snapshotTrail.at(-1)?.health ?? 0;
  const merged = new Map(snapshotTrail.map((sample) => [`${sample.tick_number}:${sample.x}:${sample.y}`, sample]));
  positions.forEach((sample, index) => {
    const entry = {
      id: -(index + 1),
      run_id: "",
      tick_number: sample.tick,
      x: sample.x ?? 0,
      y: sample.y ?? 0,
      angle: sample.angle ?? 0,
      health: latestHealth,
    };
    merged.set(`${entry.tick_number}:${entry.x}:${entry.y}`, entry);
  });
  return Array.from(merged.values()).sort((a, b) => a.tick_number - b.tick_number);
}

function RuntimeWarnings({ flags }: { flags?: Record<string, unknown> | null }) {
  const warnings = Array.isArray(flags?.warnings) ? flags.warnings.map(String) : [];
  if (warnings.length === 0) return null;
  return (
    <>
      <h2 className="mb-3 text-sm font-semibold">Runtime Warnings</h2>
      <div className="space-y-2">
        {warnings.map((warning) => (
          <div key={warning} className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            {warning}
          </div>
        ))}
      </div>
    </>
  );
}

function RunDetailContent({ runId }: { runId: string }) {
  const router = useRouter();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => apiGet<Run>(`/runs/${runId}`), refetchInterval: 5_000 });
  const defects = useQuery({ queryKey: ["run-defects", runId], queryFn: () => apiGet<Defect[]>(`/runs/${runId}/defects`) });
  const decisions = useQuery({ queryKey: ["run-decisions", runId], queryFn: () => apiGet<Decision[]>(`/runs/${runId}/decisions?page_size=500`) });
  const trail = useQuery({ queryKey: ["run-trail", runId], queryFn: () => apiGet<PositionSample[]>(`/runs/${runId}/position-trail?limit=5000`) });
  const events = useQuery({ queryKey: ["run-events", runId], queryFn: () => apiGet<TraceEntry[]>(`/runs/${runId}/events?type=kill,death,item_pickup,secret_found,stuck`) });
  const usage = useQuery({ queryKey: ["run-usage", runId], queryFn: () => apiGet<UsageStats>(`/runs/${runId}/usage`) });
  const benchmark = useQuery({ queryKey: ["run-benchmark", runId], queryFn: () => apiGet<BenchmarkStats>(`/runs/${runId}/benchmark`) });
  const reportStatus = useQuery({ queryKey: ["run-report-status", runId], queryFn: () => apiGet<ReportStatus>(`/runs/${runId}/report/status`), refetchInterval: 3_000 });
  const maps = useQuery({
    queryKey: ["run-maps", run.data?.wad_file_id],
    queryFn: () => apiGet<WadMap[]>(`/wads/${run.data?.wad_file_id}/maps`),
    enabled: Boolean(run.data?.wad_file_id),
  });
  const map = maps.data?.find((item) => item.map_name === run.data?.map_name);

  if (!run.data) {
    return <SkeletonRows />;
  }

  return (
    <div className="space-y-5 p-4 lg:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">{run.data.map_name}</h2>
          <p className="text-sm text-neutral-500">{run.data.id}</p>
          {run.data.behavior_profile ? <p className="text-xs text-neutral-400">Behavior: {run.data.behavior_profile}</p> : null}
        </div>
        <div className="flex items-center gap-2">
          <OutcomeBadge outcome={run.data.outcome ?? run.data.status} />
          <button onClick={() => router.push(`/run/${runId}`)} className="inline-flex h-10 items-center gap-2 rounded border border-neutral-300 bg-white px-3 text-sm font-semibold">
            <Activity className="h-4 w-4" aria-hidden="true" />
            Live
          </button>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <MapCanvas map={map} trail={trail.data ?? []} events={events.data ?? []} />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          <Metric label="Duration" value={run.data.duration_seconds ?? 0} />
          <Metric label="Actions" value={run.data.total_actions_taken ?? 0} />
          <Metric label="Final HP" value={run.data.final_hp ?? 0} />
          <Metric label="Kills" value={run.data.total_kills ?? 0} />
          <Metric label="Secrets" value={run.data.secrets_found ?? 0} />
          <Metric label="Defects" value={defects.data?.length ?? 0} />
        </div>
      </div>

      {usage.isLoading ? (
        <section className="rounded border border-neutral-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold">Token Usage</h2>
          <SkeletonRows />
        </section>
      ) : usage.data ? (
        <section className="rounded border border-neutral-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold">Token Usage</h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Metric label="LLM Calls" value={usage.data.total_llm_calls} />
            <Metric label="Prompt Tokens" value={usage.data.total_prompt_tokens.toLocaleString()} />
            <Metric label="Completion Tokens" value={usage.data.total_completion_tokens.toLocaleString()} />
            <Metric label="Total Tokens" value={usage.data.total_tokens.toLocaleString()} />
            <Metric label="Est. Cost" value={`$${usage.data.estimated_cost_usd.toFixed(6)}`} />
            <Metric label="Avg Cost/Decision" value={`$${usage.data.per_decision_avg_cost_usd.toFixed(8)}`} />
            <Metric label="Model" value={usage.data.model} />
          </div>
        </section>
      ) : null}

      {benchmark.isLoading ? (
        <section className="rounded border border-neutral-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold">Performance Benchmark</h2>
          <SkeletonRows />
        </section>
      ) : benchmark.data ? (
        <section className="rounded border border-neutral-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold">Performance Benchmark</h2>
          {benchmark.data.total_decisions === 0 ? (
            <p className="py-3 text-sm text-neutral-500">No data — run has no decisions</p>
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <h3 className="mb-2 text-xs font-semibold uppercase text-neutral-500">LLM Latency (ms)</h3>
                  <div className="grid grid-cols-3 gap-2">
                    <Metric label="Avg" value={`${benchmark.data.llm_latency_ms.avg.toFixed(1)}ms`} />
                    <Metric label="p50" value={`${benchmark.data.llm_latency_ms.p50.toFixed(1)}ms`} />
                    <Metric label="p95" value={`${benchmark.data.llm_latency_ms.p95.toFixed(1)}ms`} />
                    <Metric label="Min" value={`${benchmark.data.llm_latency_ms.min.toFixed(1)}ms`} />
                    <Metric label="Max" value={`${benchmark.data.llm_latency_ms.max.toFixed(1)}ms`} />
                    <Metric label="Samples" value={benchmark.data.llm_latency_ms.count} />
                  </div>
                </div>
                <div>
                  <h3 className="mb-2 text-xs font-semibold uppercase text-neutral-500">MCP Latency (ms)</h3>
                  <div className="grid grid-cols-3 gap-2">
                    <Metric label="Avg" value={`${benchmark.data.mcp_latency_ms.avg.toFixed(1)}ms`} />
                    <Metric label="p50" value={`${benchmark.data.mcp_latency_ms.p50.toFixed(1)}ms`} />
                    <Metric label="p95" value={`${benchmark.data.mcp_latency_ms.p95.toFixed(1)}ms`} />
                    <Metric label="Min" value={`${benchmark.data.mcp_latency_ms.min.toFixed(1)}ms`} />
                    <Metric label="Max" value={`${benchmark.data.mcp_latency_ms.max.toFixed(1)}ms`} />
                    <Metric label="Samples" value={benchmark.data.mcp_latency_ms.count} />
                  </div>
                </div>
              </div>
              <h3 className="mt-4 mb-2 text-xs font-semibold uppercase text-neutral-500">Tools Used</h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(benchmark.data.tools_used).map(([tool, count]) => (
                  <span key={tool} className="rounded border border-neutral-200 bg-neutral-50 px-2 py-1 text-xs">
                    {tool}: <strong>{count}</strong>
                  </span>
                ))}
              </div>
            </>
          )}
        </section>
      ) : null}

      <section>
        <RuntimeWarnings flags={run.data.agent_quality_flags} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold">Defects</h2>
        {defects.data && defects.data.length === 0 ? (
          <p className="py-6 text-sm text-neutral-500">No defects found — map passed automated checks</p>
        ) : (
          <div className="grid gap-2">
            {(defects.data ?? []).map((defect) => (
              <div key={defect.fingerprint ?? defect.title} className="rounded border border-neutral-200 bg-white p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold">{defect.title}</span>
                  <span className="text-xs text-neutral-500">S{defect.severity}</span>
                </div>
                <p className="mt-1 text-sm text-neutral-600">{defect.description}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div>
          <h2 className="mb-3 text-sm font-semibold">Decision Trace</h2>
          {decisions.data && decisions.data.length === 0 ? (
            <p className="py-6 text-sm text-neutral-500">No decisions recorded yet</p>
          ) : (
            <DecisionTimeline decisions={decisions.data ?? []} />
          )}
        </div>
        <div>
          <h2 className="mb-3 text-sm font-semibold">Recording</h2>
          {run.data.recording_mp4_url ? (
            <video className="aspect-video w-full rounded border border-neutral-200 bg-black" controls src={`${API_BASE}/runs/${runId}/recording`} />
          ) : (
            <div className="grid aspect-video w-full place-items-center rounded border border-neutral-200 bg-neutral-950 text-sm text-neutral-300">Recording not ready</div>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-neutral-500">
            <span className="rounded border border-neutral-200 bg-white px-2 py-1">Report: {reportStatus.data?.status ?? "checking"}</span>
            <span className="rounded border border-neutral-200 bg-white px-2 py-1">
              Recording: {String(run.data.recording_metadata?.quality_status ?? (run.data.recording_mp4_url ? "available" : "pending"))}
            </span>
          </div>
          {reportStatus.data?.pdf_available || run.data.report_pdf_url ? (
            <a className="mt-3 inline-flex h-10 items-center rounded bg-neutral-950 px-4 text-sm font-semibold text-white" href={`${API_BASE}/runs/${runId}/report/pdf`}>
              PDF Report
            </a>
          ) : (
            <a className="mt-3 inline-flex h-10 items-center rounded bg-neutral-700 px-4 text-sm font-semibold text-white" href={`${API_BASE}/runs/${runId}/report/pdf`}>
              Generate PDF
            </a>
          )}
        </div>
      </section>
    </div>
  );
}
