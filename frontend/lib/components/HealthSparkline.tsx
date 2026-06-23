"use client";

import { useQuery } from "@tanstack/react-query";
import { apiGet, PositionSample } from "@/lib/api";
import { sparklinePath } from "@/lib/game-utils";

export function HealthSparkline({ runId, fallback, batchTrail }: { runId: string; fallback: number; batchTrail?: PositionSample[] }) {
  const trail = useQuery({
    queryKey: ["spark", runId],
    queryFn: () => apiGet<PositionSample[]>(`/runs/${runId}/position-trail?limit=80`),
    enabled: !batchTrail,
  });
  const data = batchTrail ?? trail.data;
  const values = (data?.length ? data : [{ tick_number: 0, health: fallback }]).slice(-80).map((item) => item.health ?? fallback);
  return (
    <div className="h-9 w-32">
      <svg viewBox="0 0 128 36" className="h-9 w-32" role="img" aria-label="HP over time">
        <line x1="0" y1="35" x2="128" y2="35" stroke="#e5e5e5" />
        <path d={sparklinePath(values)} fill="none" stroke="#0891b2" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}
