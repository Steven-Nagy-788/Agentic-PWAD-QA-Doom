import { AlertTriangle } from "lucide-react";

export function DefectBadge({ count, pulse = false }: { count: number; pulse?: boolean }) {
  const tone =
    count === 0
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : count < 3
        ? "border-amber-200 bg-amber-50 text-amber-900"
        : "border-red-200 bg-red-50 text-red-900";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded border px-2.5 py-1 text-xs font-semibold ${tone} ${pulse ? "animate-pulse" : ""}`} aria-label={`${count} defect${count === 1 ? "" : "s"}`}>
      <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
      {count}
    </span>
  );
}
