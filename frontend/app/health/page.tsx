"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { API_ROOT, apiGet, apiRootGet } from "@/lib/api";
import { OutcomeBadge, errorMessage } from "@/lib/components/shared";

export default function HealthPage() {
  const queryClient = useQueryClient();
  const health = useQuery({ queryKey: ["health"], queryFn: () => apiRootGet<Record<string, unknown>>("/health"), refetchInterval: 10_000 });
  const gemini = useQuery({ queryKey: ["health-gemini"], queryFn: () => apiRootGet<Record<string, unknown>>("/health/gemini"), refetchInterval: 10_000 });
  const mcp = useQuery({ queryKey: ["health-mcp"], queryFn: () => apiRootGet<Record<string, unknown>>("/health/mcp"), refetchInterval: 10_000 });
  const storage = useQuery({ queryKey: ["storage"], queryFn: () => apiGet<Record<string, unknown>>("/admin/storage/stats"), refetchInterval: 10_000 });
  const probeGemini = useMutation({
    mutationFn: async () => {
      const response = await fetch(`${API_ROOT}/health/gemini/probe`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      return response.json() as Promise<Record<string, unknown>>;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["health-gemini"] }),
  });

  return (
    <div className="space-y-4 p-4 lg:p-6">
      <h2 className="text-xl font-semibold">Health</h2>
      <div className="grid gap-4 md:grid-cols-3">
        <HealthCard name="API" data={health.data} error={errorMessage(health.error)} />
        <HealthCard
          name="Gemini"
          data={gemini.data}
          error={errorMessage(gemini.error) ?? errorMessage(probeGemini.error)}
          action={
            <button
              type="button"
              onClick={() => probeGemini.mutate()}
              disabled={probeGemini.isPending}
              title="Probe Gemini now"
              className="grid h-8 w-8 place-items-center rounded border border-neutral-200 bg-white text-neutral-600 disabled:text-neutral-300"
            >
              <RefreshCw className={`h-4 w-4 ${probeGemini.isPending ? "animate-spin" : ""}`} />
            </button>
          }
        />
        <HealthCard name="MCP" data={mcp.data} error={errorMessage(mcp.error)} />
      </div>
      <pre className="overflow-auto rounded border border-neutral-200 bg-white p-4 text-xs">{JSON.stringify(storage.data, null, 2)}</pre>
    </div>
  );
}

function HealthCard({ name, data, error, action }: { name: string; data?: Record<string, unknown>; error?: string; action?: React.ReactNode }) {
  const status = String(data?.status ?? (error ? "error" : "loading"));
  return (
    <div className="rounded border border-neutral-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">{name}</h3>
        <div className="flex items-center gap-2">{action}<OutcomeBadge outcome={status} /></div>
      </div>
      <p className="mt-3 break-words text-sm text-neutral-600">{error ?? JSON.stringify(data ?? {})}</p>
    </div>
  );
}
