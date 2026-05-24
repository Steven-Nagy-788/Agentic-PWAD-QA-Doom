"use client";

import { useQuery } from "@tanstack/react-query";
import { apiGet, apiRootGet } from "@/lib/api";
import { OutcomeBadge, errorMessage } from "@/lib/components/shared";

export default function HealthPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: () => apiRootGet<Record<string, unknown>>("/health"), refetchInterval: 10_000 });
  const gemini = useQuery({ queryKey: ["health-gemini"], queryFn: () => apiRootGet<Record<string, unknown>>("/health/gemini"), refetchInterval: 10_000 });
  const mcp = useQuery({ queryKey: ["health-mcp"], queryFn: () => apiRootGet<Record<string, unknown>>("/health/mcp"), refetchInterval: 10_000 });
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
