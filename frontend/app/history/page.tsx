"use client";

import { useDeferredValue, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Run, RunList, WadFile, PositionSample, apiGet } from "@/lib/api";
import { InlineError, OutcomeBadge, SkeletonRows, errorMessage } from "@/lib/components/shared";
import { HealthSparkline } from "@/lib/components/HealthSparkline";

type RunFilters = { wad: string; map: string; outcome: string; difficulty: string; after: string; before: string };
const RUN_PAGE_SIZE = 20;

function normalizeRunList(data: RunList | Run[]): RunList {
  return Array.isArray(data) ? { total: data.length, items: data, offset: 0 } : data;
}

export default function RunHistoryPage() {
  const router = useRouter();
  const [filters, setFilters] = useState<RunFilters>({ wad: "", map: "", outcome: "", difficulty: "", after: "", before: "" });
  const [runOffset, setRunOffset] = useState(0);
  const deferredFilters = useDeferredValue(filters);

  const wads = useQuery({ queryKey: ["wads"], queryFn: () => apiGet<WadFile[]>("/wads") });
  const runListPath = useMemo(() => {
    const params = new URLSearchParams({ limit: String(RUN_PAGE_SIZE), offset: String(runOffset) });
    if (deferredFilters.wad) params.set("wad_file_id", deferredFilters.wad);
    if (deferredFilters.map) params.set("map_name", deferredFilters.map);
    if (deferredFilters.outcome) params.set("outcome", deferredFilters.outcome);
    if (deferredFilters.difficulty) params.set("difficulty_level", deferredFilters.difficulty);
    if (deferredFilters.after) params.set("created_after", new Date(deferredFilters.after).toISOString());
    if (deferredFilters.before) params.set("created_before", new Date(deferredFilters.before).toISOString());
    return `/runs?${params.toString()}`;
  }, [deferredFilters, runOffset]);

  const runs = useQuery({
    queryKey: ["runs", runListPath],
    queryFn: async () => normalizeRunList(await apiGet<RunList | Run[]>(runListPath)),
    refetchInterval: 10_000,
  });

  const updateFilters: React.Dispatch<React.SetStateAction<RunFilters>> = (next) => {
    setRunOffset(0);
    setFilters(next);
  };

  const visibleRuns = runs.data?.items ?? [];
  const runIds = visibleRuns.map((r) => r.id).join(",");
  const batchTrails = useQuery({
    queryKey: ["batch-trails", runIds],
    queryFn: () => apiGet<Record<string, PositionSample[]>>(`/runs/batch-trails?ids=${runIds}&limit=80`),
    enabled: visibleRuns.length > 0,
  });

  const total = runs.data?.total ?? 0;
  const rangeStart = total === 0 ? 0 : runOffset + 1;
  const rangeEnd = Math.min(runOffset + visibleRuns.length, total);
  const hasPrevious = runOffset > 0;
  const hasNext = runOffset + RUN_PAGE_SIZE < total;

  return (
    <div className="space-y-4 p-4 lg:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Run History</h2>
          <p className="text-sm text-neutral-500">Showing {rangeStart}-{rangeEnd} of {total} runs</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={!hasPrevious}
            onClick={() => setRunOffset(Math.max(runOffset - RUN_PAGE_SIZE, 0))}
            className="h-9 rounded border border-neutral-300 bg-white px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:text-neutral-300"
          >
            Previous
          </button>
          <button
            type="button"
            disabled={!hasNext}
            onClick={() => setRunOffset(runOffset + RUN_PAGE_SIZE)}
            className="h-9 rounded border border-neutral-300 bg-white px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:text-neutral-300"
          >
            Next
          </button>
        </div>
      </div>

      <div className="grid gap-2 rounded border border-neutral-200 bg-white p-3 md:grid-cols-6">
        <label className="flex h-10 items-center rounded border border-neutral-200 bg-white px-3">
          <select className="min-w-0 flex-1 bg-transparent text-sm outline-none" value={filters.wad} onChange={(event) => updateFilters((current) => ({ ...current, wad: event.target.value }))}>
            <option value="">All WADs</option>
            {(wads.data ?? []).map((wad) => <option key={wad.id} value={wad.id}>{wad.original_filename}</option>)}
          </select>
        </label>
        <FilterInput placeholder="Map" value={filters.map} onChange={(map) => updateFilters((current) => ({ ...current, map }))} />
        <FilterInput placeholder="Outcome" value={filters.outcome} onChange={(outcome) => updateFilters((current) => ({ ...current, outcome }))} />
        <FilterInput placeholder="Difficulty" value={filters.difficulty} onChange={(difficulty) => updateFilters((current) => ({ ...current, difficulty }))} />
        <DateInput value={filters.after} onChange={(after) => updateFilters((current) => ({ ...current, after }))} />
        <DateInput value={filters.before} onChange={(before) => updateFilters((current) => ({ ...current, before }))} />
      </div>

      <div className="overflow-x-auto rounded border border-neutral-200 bg-white">
        {runs.isLoading || wads.isLoading ? (
          <div className="p-3"><SkeletonRows /></div>
        ) : runs.error || wads.error ? (
          <div className="p-3"><InlineError message={errorMessage(runs.error ?? wads.error) ?? "Failed to load run history"} /></div>
        ) : visibleRuns.length === 0 ? (
          <div className="p-6 text-center text-sm text-neutral-500">
            No runs yet. Upload a WAD to get started.
          </div>
        ) : (
          <table className="min-w-full text-sm">
            <thead className="bg-neutral-50 text-left text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-3 py-3">Map</th>
                <th className="px-3 py-3">Outcome</th>
                <th className="px-3 py-3">Difficulty</th>
                <th className="px-3 py-3">HP</th>
                <th className="px-3 py-3">Created</th>
              </tr>
            </thead>
            <tbody>
              {visibleRuns.map((run) => (
                <tr key={run.id} className="border-t border-neutral-200 hover:bg-neutral-50">
                  <td className="px-3 py-3">
                    <button type="button" onClick={() => router.push(`/run/${run.id}`)} className="text-left font-semibold text-neutral-950 hover:underline">
                      {run.map_display_name || run.map_name}
                    </button>
                    {run.map_display_name ? <div className="text-xs text-neutral-500">{run.map_name}</div> : null}
                  </td>
                  <td className="px-3 py-3"><OutcomeBadge outcome={run.outcome ?? run.status} /></td>
                  <td className="px-3 py-3">{run.difficulty_level}</td>
                  <td className="px-3 py-3"><HealthSparkline runId={run.id} fallback={run.final_hp ?? 0} batchTrail={batchTrails.data?.[run.id]} /></td>
                  <td className="px-3 py-3 text-neutral-500">{new Date(run.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function FilterInput({ placeholder, value, onChange }: { placeholder: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="flex h-10 items-center gap-2 rounded border border-neutral-200 bg-white px-3">
      <input className="min-w-0 flex-1 bg-transparent text-sm outline-none" placeholder={placeholder} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function DateInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <label className="flex h-10 items-center gap-2 rounded border border-neutral-200 bg-white px-3">
      <input className="min-w-0 flex-1 bg-transparent text-sm outline-none" type="date" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
