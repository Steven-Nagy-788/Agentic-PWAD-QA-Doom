"use client";

import { use, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Play } from "lucide-react";
import { WadFile, WadMap, Run, BehaviorProfile, apiGet, apiSend } from "@/lib/api";
import { Metric, SkeletonRows, InlineError, errorMessage } from "@/lib/components/shared";
import { MapCanvas } from "@/components/MapCanvas";
import { SkillHeatmap } from "@/components/SkillHeatmap";

export default function WadDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();
  const [selectedMap, setSelectedMap] = useState<WadMap | null>(null);
  const [difficulty, setDifficulty] = useState(3);
  const [maxTicks, setMaxTicks] = useState(3000);
  const [behaviorProfile, setBehaviorProfile] = useState("thorough");

  const wad = useQuery({ queryKey: ["wad", id], queryFn: () => apiGet<WadFile>(`/wads/${id}`) });
  const maps = useQuery({ queryKey: ["wad-maps", id], queryFn: () => apiGet<WadMap[]>(`/wads/${id}/maps`) });
  const behaviorProfiles = useQuery({
    queryKey: ["behavior-profiles"],
    queryFn: () => apiGet<Record<string, BehaviorProfile>>("/settings/behavior-profiles"),
  });

  const startRun = useMutation({
    mutationFn: (input: { wad_file_id: string; map_name: string; difficulty_level: number; max_ticks: number; behavior_profile?: string }) =>
      apiSend<Run>("/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      }),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      router.push(`/run/${run.id}`);
    },
  });

  if (wad.isLoading) return <SkeletonRows />;
  if (!wad.data) return <div className="p-6 text-neutral-500">WAD not found</div>;

  return (
    <div className="grid min-h-screen grid-cols-1 gap-0 lg:grid-cols-[1fr_360px]">
      <div className="space-y-5 p-4 lg:p-6">
        <div>
          <h2 className="text-xl font-semibold">{wad.data.original_filename}</h2>
          <p className="text-sm text-neutral-500">{wad.data.iwad_required} · {maps.data?.length ?? 0} maps</p>
        </div>
        {maps.isLoading ? <SkeletonRows /> : null}
        <div className="grid gap-4 xl:grid-cols-2">
          {(maps.data ?? []).map((map) => (
            <button
              key={map.map_name}
              onClick={() => setSelectedMap(map)}
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
          <label className="block">
            <span className="mb-2 block text-xs font-semibold text-neutral-600">Agent Behavior</span>
            <select
              value={behaviorProfile}
              onChange={(event) => setBehaviorProfile(event.target.value)}
              className="w-full h-10 rounded border border-neutral-200 bg-white px-3 text-sm"
            >
              {behaviorProfiles.data
                ? Object.entries(behaviorProfiles.data).map(([key, profile]) => (
                    <option key={key} value={key}>{profile.name} — {profile.description}</option>
                  ))
                : <option value="thorough">Thorough — Slow, methodical, every corner</option>}
              <option value="fast">Fast — Cover ground quickly, breadth over depth</option>
              <option value="exploit_focused">Exploit-focused — Aggressive boundary testing</option>
            </select>
          </label>
          {startRun.error ? <InlineError message={errorMessage(startRun.error) ?? "Failed to start run"} /> : null}
          <span id="launch-description" className="sr-only">Start a new automated run on the selected map at the chosen difficulty</span>
          <button
            disabled={!selectedMap || startRun.isPending}
            onClick={() => startRun.mutate({ wad_file_id: id, map_name: selectedMap!.map_name, difficulty_level: difficulty, max_ticks: maxTicks, behavior_profile: behaviorProfile })}
            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded bg-neutral-950 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-neutral-300"
            aria-describedby="launch-description"
          >
            <Play className="h-4 w-4" aria-hidden="true" />
            {startRun.isPending ? "Launching" : "Launch"}
          </button>
        </div>
      </aside>
    </div>
  );
}
