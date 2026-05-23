"use client";

import { use } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Activity, X } from "lucide-react";
import { Run, Defect, Decision, PositionSample, TraceEntry, UsageStats, BenchmarkStats, WadMap, apiGet, apiSend, API_BASE } from "@/lib/api";
import { useRunStream } from "@/hooks/useRunStream";
import { Metric, OutcomeBadge, SkeletonRows, InlineError, errorMessage, formatTime } from "@/lib/components/shared";
import { DefectBadge } from "@/components/DefectBadge";
import { DecisionTimeline } from "@/components/DecisionTimeline";
import { MapCanvas } from "@/components/MapCanvas";
import { ReasoningLog } from "@/components/ReasoningLog";
import { StatBar } from "@/components/StatBar";

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const run = useQuery({ queryKey: ["run", id], queryFn: () => apiGet<Run>(`/runs/${id}`), refetchInterval: 8_000 });

  if (run.isLoading) return <SkeletonRows />;
  if (!run.data) return <div className="p-6 text-neutral-500">Run not found</div>;

  const isLive = run.data.status === "running" || run.data.status === "pending";
  if (isLive) {
    return <LiveRunContent runId={id} />;
  }
  return <RunDetailContent runId={id} />;
}

function LiveRunContent({ runId }: { runId: string }) {
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

  return (
    <div className="grid h-screen grid-rows-[1fr_auto]">
      <div className="grid min-h-0 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="flex min-h-0 flex-col bg-neutral-950">
          <div className="flex items-center justify-between border-b border-neutral-800 px-4 py-3 text-white">
            <span className="text-sm font-semibold" role="status" aria-live="polite">
              {stream.connected
                ? `Connected ${stream.lastMessageAt ? `(last msg: ${formatTime(stream.lastMessageAt)})` : ""}`
                : `Reconnecting (attempt ${stream.retryCount}, next in ${(stream.retryDelay / 1000).toFixed(0)}s)`}
            </span>
            <div className="flex items-center gap-3">
              <span className="text-xs text-neutral-300">
                {tt.decisionCount > 0 ? `${tt.totalTokens.toLocaleString()} tokens · $${tt.totalCost.toFixed(6)}` : ""}
              </span>
              <DefectBadge count={stream.defects.length} pulse={stream.defects.length > 0} />
              <button onClick={() => cancel.mutate()} className="inline-flex h-9 items-center gap-2 rounded border border-neutral-700 px-3 text-sm">
                <X className="h-4 w-4" aria-hidden="true" />
                Cancel
              </button>
            </div>
          </div>
          <div className="grid flex-1 place-items-center p-4">
            {stream.frame ? (
              <img src={stream.frame} alt="Live game frame" role="img" aria-label="Live game frame" className="aspect-[4/3] max-h-full max-w-full object-contain" />
            ) : (
              <div className="aspect-[4/3] w-full max-w-4xl bg-neutral-900" />
            )}
          </div>
        </div>
        <ReasoningLog decisions={stream.decisions} live />
      </div>
      <StatBar state={{ ...stream.state, secrets: stream.state?.secrets }} />
    </div>
  );
}

function RunDetailContent({ runId }: { runId: string }) {
  const router = useRouter();
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => apiGet<Run>(`/runs/${runId}`) });
  const defects = useQuery({ queryKey: ["run-defects", runId], queryFn: () => apiGet<Defect[]>(`/runs/${runId}/defects`) });
  const decisions = useQuery({ queryKey: ["run-decisions", runId], queryFn: () => apiGet<Decision[]>(`/runs/${runId}/decisions?page_size=500`) });
  const trail = useQuery({ queryKey: ["run-trail", runId], queryFn: () => apiGet<PositionSample[]>(`/runs/${runId}/position-trail`) });
  const events = useQuery({ queryKey: ["run-events", runId], queryFn: () => apiGet<TraceEntry[]>(`/runs/${runId}/events?type=kill,death,item_pickup,secret_found,stuck`) });
  const usage = useQuery({ queryKey: ["run-usage", runId], queryFn: () => apiGet<UsageStats>(`/runs/${runId}/usage`) });
  const benchmark = useQuery({ queryKey: ["run-benchmark", runId], queryFn: () => apiGet<BenchmarkStats>(`/runs/${runId}/benchmark`) });
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
          <video className="aspect-video w-full rounded border border-neutral-200 bg-black" controls src={`${API_BASE}/runs/${runId}/recording`} />
          <a className="mt-3 inline-flex h-10 items-center rounded bg-neutral-950 px-4 text-sm font-semibold text-white" href={`${API_BASE}/runs/${runId}/report/pdf`}>
            PDF Report
          </a>
        </div>
      </section>
    </div>
  );
}
