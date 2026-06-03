"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AppSettings, BehaviorProfile, apiGet, apiSend } from "@/lib/api";
import { SkeletonRows, InlineError, errorMessage } from "@/lib/components/shared";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => apiGet<AppSettings>("/settings") });
  const profiles = useQuery({
    queryKey: ["behavior-profiles"],
    queryFn: () => apiGet<Record<string, BehaviorProfile>>("/settings/behavior-profiles"),
  });
  const [editMode, setEditMode] = useState(false);
  const [draft, setDraft] = useState<Partial<AppSettings>>({});
  const saveMutation = useMutation({
    mutationFn: (dirty: Partial<AppSettings>) => {
      const clean: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(dirty)) {
        if (!settings.data?.sources[key]) continue;
        if (value === "" || value === undefined || value === null) continue;
        if (value === settings.data[key as keyof AppSettings]) continue;
        clean[key] = value;
      }
      return apiSend<AppSettings>("/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(clean),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setEditMode(false);
    },
  });
  const resetModelMutation = useMutation({
    mutationFn: () => apiSend<AppSettings>("/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clear_overrides: ["llm_model"] }),
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
  const startEdit = () => {
    if (settings.data) {
      setDraft({ ...settings.data });
      setEditMode(true);
    }
  };
  const cancelEdit = () => {
    if (settings.data) {
      setDraft({ ...settings.data });
    }
    setEditMode(false);
  };

  return (
    <div className="space-y-6 p-4 lg:p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Settings</h2>
        {editMode ? (
          <div className="flex items-center gap-2">
            <button onClick={cancelEdit} className="inline-flex h-9 items-center rounded border border-neutral-300 bg-white px-3 text-sm font-semibold">
              Cancel
            </button>
            <button
              onClick={() => saveMutation.mutate(draft)}
              disabled={saveMutation.isPending}
              className="inline-flex h-9 items-center rounded bg-neutral-950 px-3 text-sm font-semibold text-white disabled:bg-neutral-300"
            >
              {saveMutation.isPending ? "Saving" : "Save"}
            </button>
          </div>
        ) : (
          <button onClick={startEdit} className="inline-flex h-9 items-center rounded border border-neutral-300 bg-white px-3 text-sm font-semibold">
            Edit
          </button>
        )}
      </div>
      {saveMutation.error ? <InlineError message={errorMessage(saveMutation.error) ?? "Failed to save"} /> : null}
      {settings.isLoading ? <SkeletonRows /> : null}
      {settings.data ? (
        <div className="grid gap-4 md:grid-cols-2">
          <SettingsCard title="LLM Config">
            <SettingsRow label="Model" value={settings.data.llm_model} edit={editMode} inputValue={draft.llm_model} onChange={(v) => setDraft((d) => ({ ...d, llm_model: v }))} />
            <p className="text-xs text-neutral-500">
              Source: {settings.data.sources.llm_model.replace("_", " ")}. Environment default: {String(settings.data.env_defaults.llm_model)}.
            </p>
            {settings.data.sources.llm_model === "database_override" ? (
              <button onClick={() => resetModelMutation.mutate()} className="text-xs font-semibold text-cyan-700 hover:underline">
                Reset model override to .env
              </button>
            ) : null}
            <SettingsRow label="Throttle (s)" value={`${settings.data.llm_throttle_seconds}s`} edit={editMode} inputValue={String(draft.llm_throttle_seconds ?? "")} onChange={(v) => setDraft((d) => ({ ...d, llm_throttle_seconds: Number(v) }))} />
            <SettingsRow label="Rate limit / min" value={String(settings.data.gemini_rate_limit_calls_per_minute)} edit={editMode} inputValue={String(draft.gemini_rate_limit_calls_per_minute ?? "")} onChange={(v) => setDraft((d) => ({ ...d, gemini_rate_limit_calls_per_minute: Number(v) }))} />
            <SettingsRow label="Input $/1M" value={`$${settings.data.llm_input_cost_per_million}`} edit={editMode} inputValue={String(draft.llm_input_cost_per_million ?? "")} onChange={(v) => setDraft((d) => ({ ...d, llm_input_cost_per_million: Number(v) }))} />
            <SettingsRow label="Output $/1M" value={`$${settings.data.llm_output_cost_per_million}`} edit={editMode} inputValue={String(draft.llm_output_cost_per_million ?? "")} onChange={(v) => setDraft((d) => ({ ...d, llm_output_cost_per_million: Number(v) }))} />
          </SettingsCard>
          <SettingsCard title="Run Config">
            <SettingsRow label="Default ticks" value={String(settings.data.default_run_ticks)} edit={editMode} inputValue={String(draft.default_run_ticks ?? "")} onChange={(v) => setDraft((d) => ({ ...d, default_run_ticks: Number(v) }))} />
            <SettingsRow label="Max ticks" value={String(settings.data.max_run_ticks)} edit={editMode} inputValue={String(draft.max_run_ticks ?? "")} onChange={(v) => setDraft((d) => ({ ...d, max_run_ticks: Number(v) }))} />
            <SettingsRow label="Default behavior" value={settings.data.default_agent_behavior} edit={editMode} inputValue={draft.default_agent_behavior} onChange={(v) => setDraft((d) => ({ ...d, default_agent_behavior: v }))} />
            <div className="flex justify-between text-sm items-center gap-2">
              <span className="text-neutral-500 shrink-0">Cross-run memory</span>
              <button
                type="button"
                role="switch"
                aria-checked={settings.data.cross_run_memory_enabled}
                onClick={() => {
                  if (editMode) {
                    setDraft((d) => ({ ...d, cross_run_memory_enabled: !settings.data.cross_run_memory_enabled }));
                  }
                }}
                className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors ${
                  settings.data.cross_run_memory_enabled ? "bg-emerald-600" : "bg-neutral-300"
                } ${editMode ? "cursor-pointer" : "cursor-not-allowed opacity-60"}`}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                    settings.data.cross_run_memory_enabled ? "translate-x-4.5" : "translate-x-0.5"
                  }`}
                />
              </button>
            </div>
            <p className="text-xs text-neutral-400 mt-1">
              Injects hypotheses and danger zones from previous runs. May improve navigation but can cause stale guidance.
            </p>
          </SettingsCard>
          <SettingsCard title="Recording Config">
            <SettingsRow label="Live FPS" value={String(settings.data.live_frame_fps)} edit={editMode} inputValue={String(draft.live_frame_fps ?? "")} onChange={(v) => setDraft((d) => ({ ...d, live_frame_fps: Number(v) }))} />
            <SettingsRow label="Recording FPS" value={String(settings.data.recording_fps)} edit={editMode} inputValue={String(draft.recording_fps ?? "")} onChange={(v) => setDraft((d) => ({ ...d, recording_fps: Number(v) }))} />
            <SettingsRow label="Telemetry stride" value={String(settings.data.recording_telemetry_stride)} edit={editMode} inputValue={String(draft.recording_telemetry_stride ?? "")} onChange={(v) => setDraft((d) => ({ ...d, recording_telemetry_stride: Number(v) }))} />
          </SettingsCard>
          <SettingsCard title="General">
            <SettingsRow label="App name" value={settings.data.app_name} />
            <SettingsRow label="Environment" value={settings.data.app_env} />
            <SettingsRow label="IWAD" value={settings.data.iwad_used} edit={editMode} inputValue={draft.iwad_used} onChange={(v) => setDraft((d) => ({ ...d, iwad_used: v }))} />
          </SettingsCard>
        </div>
      ) : null}
      {settings.error ? <InlineError message={errorMessage(settings.error) ?? "Failed to load settings"} /> : null}

      <h3 className="text-lg font-semibold pt-2">Behavior Profiles</h3>
      {profiles.isLoading ? <SkeletonRows /> : null}
      {profiles.data ? (
        <div className="grid gap-4 md:grid-cols-3">
          {Object.entries(profiles.data).map(([key, profile]) => (
            <div key={key} className="rounded border border-neutral-200 bg-white p-4">
              <h4 className="font-semibold capitalize mb-2">{profile.name}</h4>
              <p className="text-sm text-neutral-600 mb-3">{profile.description}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function SettingsCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded border border-neutral-200 bg-white p-4">
      <h3 className="font-semibold text-sm mb-3">{title}</h3>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function SettingsRow({ label, value, edit, inputValue, onChange }: { label: string; value: string; edit?: boolean; inputValue?: string; onChange?: (v: string) => void }) {
  return (
    <div className="flex justify-between text-sm items-center gap-2">
      <span className="text-neutral-500 shrink-0">{label}</span>
      {edit && onChange !== undefined ? (
        <input
          className="min-w-0 flex-1 rounded border border-neutral-200 px-2 py-1 text-right font-medium text-neutral-950 text-sm bg-white"
          value={inputValue ?? value}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <span className="font-medium text-neutral-950 truncate ml-2">{value}</span>
      )}
    </div>
  );
}
