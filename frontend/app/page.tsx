"use client";

/* eslint-disable @next/next/no-img-element */

import { useMemo, useState, useSyncExternalStore } from "react";
import type React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, FileArchive, HeartPulse, History, Play, Search, Upload, X } from "lucide-react";
import { DefectBadge } from "@/components/DefectBadge";
import { DecisionTimeline } from "@/components/DecisionTimeline";
import { MapCanvas } from "@/components/MapCanvas";
import { ReasoningLog } from "@/components/ReasoningLog";
import { SkillHeatmap } from "@/components/SkillHeatmap";
import { StatBar } from "@/components/StatBar";
import { useRunStream } from "@/hooks/useRunStream";
import {
  API_BASE,
  Defect,
  Decision,
  PositionSample,
  Run,
  RunList,
  TraceEntry,
  WadFile,
  WadMap,
  apiGet,
  apiSend,
  assetUrl,
  uploadWad,
} from "@/lib/api";

type View = "library" | "wad" | "live" | "run" | "history" | "health";
type RunFilters = { wad: string; map: string; outcome: string; difficulty: string; after: string; before: string };
const RUN_PAGE_SIZE = 20;

export default function Home() {
  const mounted = useClientMounted();
  return mounted ? <Dashboard /> : <AppLoadingShell />;
}

function useClientMounted() {
  return useSyncExternalStore(noopSubscribe, () => true, () => false);
}

function noopSubscribe() {
  return () => {};
}

function Dashboard() {
  const queryClient = useQueryClient();
  const [view, setView] = useState<View>("library");
  const [selectedWad, setSelectedWad] = useState<WadFile | null>(null);
  const [selectedMap, setSelectedMap] = useState<WadMap | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [detailRunId, setDetailRunId] = useState<string | null>(null);
  const [filters, setFilters] = useState<RunFilters>({ wad: "", map: "", outcome: "", difficulty: "", after: "", before: "" });
  const [runOffset, setRunOffset] = useState(0);

  const wads = useQuery({ queryKey: ["wads"], queryFn: () => apiGet<WadFile[]>("/wads") });
  const maps = useQuery({
    queryKey: ["wad-maps", selectedWad?.id],
    queryFn: () => apiGet<WadMap[]>(`/wads/${selectedWad?.id}/maps`),
    enabled: Boolean(selectedWad?.id),
  });
  const runListPath = useMemo(() => {
    const params = new URLSearchParams({ limit: String(RUN_PAGE_SIZE), offset: String(runOffset) });
    if (filters.map) params.set("map_name", filters.map);
    if (filters.outcome) params.set("outcome", filters.outcome);
    if (filters.difficulty) params.set("difficulty_level", filters.difficulty);
    if (filters.after) params.set("created_after", new Date(filters.after).toISOString());
    if (filters.before) params.set("created_before", new Date(filters.before).toISOString());
    return `/runs?${params.toString()}`;
  }, [filters, runOffset]);
  const runs = useQuery({
    queryKey: ["runs", runListPath],
    queryFn: async () => normalizeRunList(await apiGet<RunList | Run[]>(runListPath)),
    refetchInterval: view === "history" ? 10_000 : false,
  });

  const updateFilters: React.Dispatch<React.SetStateAction<RunFilters>> = (next) => {
    setRunOffset(0);
    setFilters(next);
  };

  const uploadMutation = useMutation({
    mutationFn: uploadWad,
    onSuccess: (wad) => {
      queryClient.invalidateQueries({ queryKey: ["wads"] });
      setSelectedWad(wad);
      setView("wad");
    },
  });
  const startRun = useMutation({
    mutationFn: (input: { wad_file_id: string; map_name: string; difficulty_level: number; max_ticks: number }) =>
      apiSend<Run>("/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      }),
    onSuccess: (run) => {
      setActiveRunId(run.id);
      setDetailRunId(run.id);
      setView("live");
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  const visibleRuns = useMemo(() => {
    const source = runs.data?.items ?? [];
    const wadFilter = filters.wad.toLowerCase();
    if (!wadFilter) return source;
    const wadIds = new Set((wads.data ?? []).filter((wad) => wad.original_filename.toLowerCase().includes(wadFilter)).map((wad) => wad.id));
    return source.filter((run) => wadIds.has(run.wad_file_id));
  }, [filters.wad, runs.data?.items, wads.data]);

  return (
    <main className="min-h-screen bg-neutral-100 text-neutral-950">
      <div className="grid min-h-screen grid-cols-1 md:grid-cols-[236px_1fr]">
        <aside className="border-b border-neutral-200 bg-white md:border-b-0 md:border-r">
          <div className="border-b border-neutral-200 p-4">
            <h1 className="text-lg font-semibold tracking-normal">Agentic PWAD QA Doom</h1>
            <p className="mt-1 text-xs text-neutral-500">{API_BASE}</p>
          </div>
          <nav className="grid grid-cols-3 gap-1 p-3 md:grid-cols-1">
            <NavButton icon={<FileArchive />} label="WADs" active={view === "library" || view === "wad"} onClick={() => setView("library")} />
            <NavButton icon={<Activity />} label="Live" active={view === "live"} onClick={() => setView("live")} disabled={!activeRunId} />
            <NavButton icon={<History />} label="Runs" active={view === "history"} onClick={() => setView("history")} />
            <NavButton icon={<HeartPulse />} label="Health" active={view === "health"} onClick={() => setView("health")} />
          </nav>
        </aside>
        <section className="min-w-0">
          {view === "library" ? (
            <WadLibrary
              wads={wads.data ?? []}
              loading={wads.isLoading}
              error={errorMessage(wads.error)}
              uploading={uploadMutation.isPending}
              uploadError={errorMessage(uploadMutation.error)}
              onUpload={(file) => uploadMutation.mutate(file)}
              onSelect={(wad) => {
                setSelectedWad(wad);
                setSelectedMap(null);
                setView("wad");
              }}
            />
          ) : null}
          {view === "wad" && selectedWad ? (
            <WadDetail
              wad={selectedWad}
              maps={maps.data ?? []}
              loading={maps.isLoading}
              selectedMap={selectedMap}
              onSelectMap={setSelectedMap}
              onStart={(difficulty, maxTicks) => {
                if (!selectedMap) return;
                startRun.mutate({
                  wad_file_id: selectedWad.id,
                  map_name: selectedMap.map_name,
                  difficulty_level: difficulty,
                  max_ticks: maxTicks,
                });
              }}
              starting={startRun.isPending}
              startError={errorMessage(startRun.error)}
            />
          ) : null}
          {view === "live" ? <LiveRun runId={activeRunId ?? detailRunId} onCancel={() => setActiveRunId(null)} /> : null}
          {view === "run" && detailRunId ? <RunDetail runId={detailRunId} onLive={() => setView("live")} /> : null}
          {view === "history" ? (
            <RunHistory
              runs={visibleRuns}
              total={runs.data?.total ?? 0}
              offset={runs.data?.offset ?? runOffset}
              pageSize={RUN_PAGE_SIZE}
              filters={filters}
              setFilters={updateFilters}
              onPageChange={setRunOffset}
              onOpen={(run) => {
                setDetailRunId(run.id);
                setView("run");
              }}
            />
          ) : null}
          {view === "health" ? <HealthDashboard /> : null}
        </section>
      </div>
    </main>
  );
}

function AppLoadingShell() {
  return (
    <main className="min-h-screen bg-neutral-100 text-neutral-950">
      <div className="grid min-h-screen grid-cols-1 md:grid-cols-[236px_1fr]">
        <aside className="border-b border-neutral-200 bg-white md:border-b-0 md:border-r">
          <div className="border-b border-neutral-200 p-4">
            <h1 className="text-lg font-semibold tracking-normal">Agentic PWAD QA Doom</h1>
            <p className="mt-1 text-xs text-neutral-500">{API_BASE}</p>
          </div>
          <nav className="grid grid-cols-3 gap-1 p-3 md:grid-cols-1">
            <div className="h-10 rounded bg-neutral-950" />
            <div className="h-10 rounded bg-neutral-100" />
            <div className="h-10 rounded bg-neutral-100" />
            <div className="h-10 rounded bg-neutral-100" />
          </nav>
        </aside>
        <section className="space-y-4 p-4 lg:p-6">
          <div className="h-8 w-40 rounded bg-neutral-200" />
          <SkeletonRows />
        </section>
      </div>
    </main>
  );
}

function WadLibrary({
  wads,
  loading,
  error,
  uploading,
  uploadError,
  onUpload,
  onSelect,
}: {
  wads: WadFile[];
  loading: boolean;
  error?: string;
  uploading: boolean;
  uploadError?: string;
  onUpload: (file: File) => void;
  onSelect: (wad: WadFile) => void;
}) {
  return (
    <div className="space-y-5 p-4 lg:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">WAD Library</h2>
          <p className="text-sm text-neutral-500">{wads.length} files</p>
        </div>
        <UploadZone busy={uploading} onUpload={onUpload} />
      </div>
      {uploadError ? <InlineError message={uploadError} /> : null}
      {error ? <InlineError message={error} /> : null}
      {loading ? <SkeletonRows /> : null}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {wads.map((wad) => (
          <button key={wad.id} onClick={() => onSelect(wad)} className="overflow-hidden rounded border border-neutral-200 bg-white text-left shadow-sm transition hover:border-neutral-400">
            <WadThumbnail wadId={wad.id} />
            <div className="space-y-3 p-4">
              <div>
                <h3 className="truncate text-sm font-semibold">{wad.original_filename}</h3>
                <p className="text-xs text-neutral-500">{formatBytes(wad.file_size_bytes)} · {wad.iwad_required}</p>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <Metric label="Maps" value={wad.detected_maps?.length ?? 0} />
                <Metric label="Uploaded" value={new Date(wad.uploaded_at).toLocaleDateString()} />
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function WadThumbnail({ wadId }: { wadId: string }) {
  const maps = useQuery({ queryKey: ["wad-thumb", wadId], queryFn: () => apiGet<WadMap[]>(`/wads/${wadId}/maps`) });
  const first = maps.data?.[0];
  return (
    <div className="aspect-[16/9] bg-neutral-950">
      {first?.map_overview_png_url ? <img src={assetUrl(first.map_overview_png_url)} alt={first.map_name} className="h-full w-full object-cover" /> : null}
    </div>
  );
}

function UploadZone({ busy, onUpload }: { busy: boolean; onUpload: (file: File) => void }) {
  const pick = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) onUpload(file);
  };
  const drop = (event: React.DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) onUpload(file);
  };
  return (
    <label
      onDragOver={(event) => event.preventDefault()}
      onDrop={drop}
      className="inline-flex h-11 cursor-pointer items-center gap-2 rounded border border-neutral-300 bg-white px-4 text-sm font-semibold hover:border-neutral-500"
    >
      <Upload className="h-4 w-4" aria-hidden="true" />
      {busy ? "Uploading" : "Upload"}
      <input className="sr-only" type="file" accept=".wad" onChange={pick} />
    </label>
  );
}

function WadDetail({
  wad,
  maps,
  loading,
  selectedMap,
  onSelectMap,
  onStart,
  starting,
  startError,
}: {
  wad: WadFile;
  maps: WadMap[];
  loading: boolean;
  selectedMap: WadMap | null;
  onSelectMap: (map: WadMap) => void;
  onStart: (difficulty: number, maxTicks: number) => void;
  starting: boolean;
  startError?: string;
}) {
  const [difficulty, setDifficulty] = useState(3);
  const [maxTicks, setMaxTicks] = useState(3000);
  return (
    <div className="grid min-h-screen grid-cols-1 gap-0 lg:grid-cols-[1fr_360px]">
      <div className="space-y-5 p-4 lg:p-6">
        <div>
          <h2 className="text-xl font-semibold">{wad.original_filename}</h2>
          <p className="text-sm text-neutral-500">{wad.iwad_required} · {maps.length} maps</p>
        </div>
        {loading ? <SkeletonRows /> : null}
        <div className="grid gap-4 xl:grid-cols-2">
          {maps.map((map) => (
            <button
              key={map.map_name}
              onClick={() => onSelectMap(map)}
              className={`rounded border bg-white p-4 text-left shadow-sm transition ${selectedMap?.map_name === map.map_name ? "border-cyan-500" : "border-neutral-200 hover:border-neutral-400"}`}
            >
              <div className="grid grid-cols-[112px_1fr] gap-4">
                <MapCanvas map={map} className="rounded" />
                <div className="min-w-0 space-y-3">
                  <div>
                    <h3 className="truncate text-sm font-semibold">{map.map_display_name ?? map.map_name}</h3>
                    <span className="mt-1 inline-flex rounded border border-neutral-200 px-2 py-0.5 text-xs text-neutral-700">{map.estimated_difficulty ?? "unknown"}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <Metric label="Enemies" value={map.thing_count_enemies ?? 0} />
                    <Metric label="Items" value={map.thing_count_items ?? 0} />
                    <Metric label="Secrets" value={map.secret_sector_count ?? 0} />
                  </div>
                  <SkillHeatmap summary={map.spawn_summary_by_skill ?? undefined} />
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>
      <aside className="border-l border-neutral-200 bg-white p-4 lg:sticky lg:top-0 lg:h-screen">
        <div className="space-y-4">
          <h2 className="text-sm font-semibold">Start Run</h2>
          <MapCanvas map={selectedMap} />
          <div>
            <label className="mb-2 block text-xs font-semibold text-neutral-600">Difficulty</label>
            <div className="grid grid-cols-5 gap-1">
              {[1, 2, 3, 4, 5].map((skill) => (
                <button
                  key={skill}
                  onClick={() => setDifficulty(skill)}
                  className={`h-9 rounded border text-sm font-semibold ${difficulty === skill ? "border-cyan-600 bg-cyan-50 text-cyan-900" : "border-neutral-200 bg-white"}`}
                >
                  {skill}
                </button>
              ))}
            </div>
          </div>
          <label className="block">
            <span className="mb-2 block text-xs font-semibold text-neutral-600">Max ticks · {maxTicks}</span>
            <input className="w-full accent-cyan-700" type="range" min="500" max="35000" step="500" value={maxTicks} onChange={(event) => setMaxTicks(Number(event.target.value))} />
          </label>
          {startError ? <InlineError message={startError} /> : null}
          <button
            disabled={!selectedMap || starting}
            onClick={() => onStart(difficulty, maxTicks)}
            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded bg-neutral-950 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-neutral-300"
          >
            <Play className="h-4 w-4" aria-hidden="true" />
            {starting ? "Launching" : "Launch"}
          </button>
        </div>
      </aside>
    </div>
  );
}

function LiveRun({ runId, onCancel }: { runId?: string | null; onCancel: () => void }) {
  const stream = useRunStream(runId ?? undefined);
  const queryClient = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => apiSend<Run>(`/runs/${runId}`, { method: "DELETE" }),
    onSuccess: () => {
      onCancel();
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
  if (!runId) {
    return <EmptyState title="No active run" />;
  }
  return (
    <div className="grid h-screen grid-rows-[1fr_auto]">
      <div className="grid min-h-0 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="flex min-h-0 flex-col bg-neutral-950">
          <div className="flex items-center justify-between border-b border-neutral-800 px-4 py-3 text-white">
            <span className="text-sm font-semibold">{stream.connected ? "Connected" : "Reconnecting"}</span>
            <div className="flex items-center gap-2">
              <DefectBadge count={stream.defects.length} pulse={stream.defects.length > 0} />
              <button onClick={() => cancel.mutate()} className="inline-flex h-9 items-center gap-2 rounded border border-neutral-700 px-3 text-sm">
                <X className="h-4 w-4" aria-hidden="true" />
                Cancel
              </button>
            </div>
          </div>
          <div className="grid flex-1 place-items-center p-4">
            {stream.frame ? <img src={stream.frame} alt="Live game frame" className="aspect-[4/3] max-h-full max-w-full object-contain" /> : <div className="aspect-[4/3] w-full max-w-4xl bg-neutral-900" />}
          </div>
        </div>
        <ReasoningLog decisions={stream.decisions} live />
      </div>
      <StatBar state={{ ...stream.state, secrets: stream.state?.secrets }} />
    </div>
  );
}

function RunDetail({ runId, onLive }: { runId: string; onLive: () => void }) {
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => apiGet<Run>(`/runs/${runId}`), refetchInterval: 8_000 });
  const defects = useQuery({ queryKey: ["run-defects", runId], queryFn: () => apiGet<Defect[]>(`/runs/${runId}/defects`) });
  const decisions = useQuery({ queryKey: ["run-decisions", runId], queryFn: () => apiGet<Decision[]>(`/runs/${runId}/decisions?page_size=500`) });
  const trail = useQuery({ queryKey: ["run-trail", runId], queryFn: () => apiGet<PositionSample[]>(`/runs/${runId}/position-trail`) });
  const events = useQuery({ queryKey: ["run-events", runId], queryFn: () => apiGet<TraceEntry[]>(`/runs/${runId}/events?type=kill,death,item_pickup,secret_found,stuck`) });
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
        </div>
        <div className="flex items-center gap-2">
          <OutcomeBadge outcome={run.data.outcome ?? run.data.status} />
          <button onClick={onLive} className="inline-flex h-10 items-center gap-2 rounded border border-neutral-300 bg-white px-3 text-sm font-semibold">
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
      <section>
        <h2 className="mb-3 text-sm font-semibold">Defects</h2>
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
      </section>
      <section className="grid gap-4 lg:grid-cols-2">
        <div>
          <h2 className="mb-3 text-sm font-semibold">Decision Trace</h2>
          <DecisionTimeline decisions={decisions.data ?? []} />
        </div>
        <div>
          <h2 className="mb-3 text-sm font-semibold">Recording</h2>
          <video className="aspect-video w-full rounded border border-neutral-200 bg-black" controls src={`${API_BASE}/runs/${runId}/recording`} />
          <a className="mt-3 inline-flex h-10 items-center rounded bg-neutral-950 px-4 text-sm font-semibold text-white" href={`${API_BASE}/runs/${runId}/report/pdf`}>
            PDF
          </a>
        </div>
      </section>
    </div>
  );
}

function RunHistory({
  runs,
  total,
  offset,
  pageSize,
  filters,
  setFilters,
  onPageChange,
  onOpen,
}: {
  runs: Run[];
  total: number;
  offset: number;
  pageSize: number;
  filters: RunFilters;
  setFilters: React.Dispatch<React.SetStateAction<RunFilters>>;
  onPageChange: (offset: number) => void;
  onOpen: (run: Run) => void;
}) {
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + runs.length, total);
  const hasPrevious = offset > 0;
  const hasNext = offset + pageSize < total;
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
            onClick={() => onPageChange(Math.max(offset - pageSize, 0))}
            className="h-9 rounded border border-neutral-300 bg-white px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:text-neutral-300"
          >
            Previous
          </button>
          <button
            type="button"
            disabled={!hasNext}
            onClick={() => onPageChange(offset + pageSize)}
            className="h-9 rounded border border-neutral-300 bg-white px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:text-neutral-300"
          >
            Next
          </button>
        </div>
      </div>
      <div className="grid gap-2 rounded border border-neutral-200 bg-white p-3 md:grid-cols-6">
        <FilterInput icon={<Search />} placeholder="WAD" value={filters.wad} onChange={(wad) => setFilters((current) => ({ ...current, wad }))} />
        <FilterInput placeholder="Map" value={filters.map} onChange={(map) => setFilters((current) => ({ ...current, map }))} />
        <FilterInput placeholder="Outcome" value={filters.outcome} onChange={(outcome) => setFilters((current) => ({ ...current, outcome }))} />
        <FilterInput placeholder="Difficulty" value={filters.difficulty} onChange={(difficulty) => setFilters((current) => ({ ...current, difficulty }))} />
        <DateInput value={filters.after} onChange={(after) => setFilters((current) => ({ ...current, after }))} />
        <DateInput value={filters.before} onChange={(before) => setFilters((current) => ({ ...current, before }))} />
      </div>
      <div className="overflow-x-auto rounded border border-neutral-200 bg-white">
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
            {runs.map((run) => (
              <tr key={run.id} className="border-t border-neutral-200 hover:bg-neutral-50">
                <td className="px-3 py-3">
                  <button type="button" onClick={() => onOpen(run)} className="text-left font-semibold text-neutral-950 hover:underline">
                    {run.map_name}
                  </button>
                </td>
                <td className="px-3 py-3"><OutcomeBadge outcome={run.outcome ?? run.status} /></td>
                <td className="px-3 py-3">{run.difficulty_level}</td>
                <td className="px-3 py-3"><HealthSparkline runId={run.id} fallback={run.final_hp ?? 0} /></td>
                <td className="px-3 py-3 text-neutral-500">{new Date(run.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function HealthDashboard() {
  const health = useQuery({ queryKey: ["health"], queryFn: () => apiGet<Record<string, unknown>>("/health"), refetchInterval: 10_000 });
  const gemini = useQuery({ queryKey: ["health-gemini"], queryFn: () => apiGet<Record<string, unknown>>("/health/gemini"), refetchInterval: 10_000 });
  const mcp = useQuery({ queryKey: ["health-mcp"], queryFn: () => apiGet<Record<string, unknown>>("/health/mcp"), refetchInterval: 10_000 });
  const storage = useQuery({ queryKey: ["storage"], queryFn: () => apiGet<Record<string, unknown>>("/admin/storage/stats"), refetchInterval: 10_000 });
  return (
    <div className="space-y-4 p-4 lg:p-6">
      <h2 className="text-xl font-semibold">Health</h2>
      <div className="grid gap-4 md:grid-cols-3">
        <HealthCard name="API" data={health.data} error={errorMessage(health.error)} />
        <HealthCard name="Gemini" data={gemini.data} error={errorMessage(gemini.error)} />
        <HealthCard name="MCP" data={mcp.data} error={errorMessage(mcp.error)} />
      </div>
      <pre className="overflow-auto rounded border border-neutral-200 bg-white p-4 text-xs">{JSON.stringify(storage.data, null, 2)}</pre>
    </div>
  );
}

function HealthCard({ name, data, error }: { name: string; data?: Record<string, unknown>; error?: string }) {
  const status = String(data?.status ?? (error ? "error" : "loading"));
  return (
    <div className="rounded border border-neutral-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">{name}</h3>
        <OutcomeBadge outcome={status} />
      </div>
      <p className="mt-3 break-words text-sm text-neutral-600">{error ?? JSON.stringify(data ?? {})}</p>
    </div>
  );
}

function HealthSparkline({ runId, fallback }: { runId: string; fallback: number }) {
  const trail = useQuery({ queryKey: ["spark", runId], queryFn: () => apiGet<PositionSample[]>(`/runs/${runId}/position-trail`) });
  const values = (trail.data?.length ? trail.data : [{ tick_number: 0, health: fallback }]).slice(-80).map((item) => item.health ?? fallback);
  const path = sparklinePath(values);
  return (
    <div className="h-9 w-32">
      <svg viewBox="0 0 128 36" className="h-9 w-32" role="img" aria-label="HP over time">
        <line x1="0" y1="35" x2="128" y2="35" stroke="#e5e5e5" />
        <path d={path} fill="none" stroke="#0891b2" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}

function NavButton({ icon, label, active, disabled, onClick }: { icon: React.ReactElement; label: string; active: boolean; disabled?: boolean; onClick: () => void }) {
  return (
    <button
      disabled={Boolean(disabled)}
      onClick={onClick}
      className={`flex h-10 items-center gap-2 rounded px-3 text-sm font-semibold disabled:cursor-not-allowed disabled:text-neutral-300 ${active ? "bg-neutral-950 text-white" : "text-neutral-700 hover:bg-neutral-100"}`}
    >
      <span className="[&>svg]:h-4 [&>svg]:w-4">{icon}</span>
      {label}
    </button>
  );
}

function FilterInput({ icon, placeholder, value, onChange }: { icon?: React.ReactElement; placeholder: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="flex h-10 items-center gap-2 rounded border border-neutral-200 bg-white px-3">
      {icon ? <span className="text-neutral-400 [&>svg]:h-4 [&>svg]:w-4">{icon}</span> : null}
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

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded border border-neutral-200 bg-neutral-50 px-3 py-2">
      <span className="block text-[11px] font-medium uppercase text-neutral-500">{label}</span>
      <span className="block truncate text-sm font-semibold text-neutral-950">{value}</span>
    </div>
  );
}

function OutcomeBadge({ outcome }: { outcome?: string | null }) {
  const value = outcome ?? "unknown";
  const tone = value === "map_completed" || value === "ok" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : value === "pwad_crash" || value === "error" ? "border-red-200 bg-red-50 text-red-800" : "border-amber-200 bg-amber-50 text-amber-900";
  return <span className={`inline-flex rounded border px-2.5 py-1 text-xs font-semibold ${tone}`}>{value}</span>;
}

function InlineError({ message }: { message: string }) {
  return <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{message}</div>;
}

function EmptyState({ title }: { title: string }) {
  return <div className="grid min-h-screen place-items-center p-6 text-sm text-neutral-500">{title}</div>;
}

function SkeletonRows() {
  return (
    <div className="space-y-2">
      {[0, 1, 2].map((item) => (
        <div key={item} className="h-20 animate-pulse rounded border border-neutral-200 bg-white" />
      ))}
    </div>
  );
}

function normalizeRunList(data: RunList | Run[]): RunList {
  return Array.isArray(data) ? { total: data.length, items: data, offset: 0 } : data;
}

function errorMessage(error: unknown): string | undefined {
  return error instanceof Error ? error.message : undefined;
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function sparklinePath(values: number[], width = 128, height = 36) {
  if (!values.length) return "";
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 100);
  const range = Math.max(max - min, 1);
  const points = values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
    const y = height - 2 - ((value - min) / range) * (height - 4);
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return points.join(" ");
}
