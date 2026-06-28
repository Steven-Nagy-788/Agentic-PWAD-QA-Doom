"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  FolderArchive,
  Play,
  AlertTriangle,
  Target,
  Crosshair,
  DollarSign,
} from "lucide-react";
import {
  fetchDashboardStats,
  fetchDashboardRecentRuns,
  fetchDashboardDefectSummary,
  type DashboardStats,
  type DashboardRecentRun,
  type DashboardDefectSummary,
} from "@/lib/api";
import {
  OutcomeBadge,
  SkeletonRows,
  errorMessage,
  formatTime,
} from "@/lib/components/shared";

export default function DashboardPage() {
  const stats = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: fetchDashboardStats,
    refetchInterval: 30000,
  });
  const recentRuns = useQuery({
    queryKey: ["dashboard-recent-runs"],
    queryFn: () => fetchDashboardRecentRuns(10),
    refetchInterval: 30000,
  });
  const defectSummary = useQuery({
    queryKey: ["dashboard-defect-summary"],
    queryFn: fetchDashboardDefectSummary,
    refetchInterval: 30000,
  });

  const loading = stats.isLoading || recentRuns.isLoading || defectSummary.isLoading;
  const error = stats.error || recentRuns.error || defectSummary.error;

  return (
    <div className="space-y-6 p-4 lg:p-6">
      <div>
        <h2 className="text-xl font-semibold">Dashboard</h2>
        <p className="text-sm text-neutral-500">System overview and QA metrics</p>
      </div>

      {error ? (
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {errorMessage(error) ?? "Failed to load dashboard data"}
        </div>
      ) : null}

      {loading ? <SkeletonRows /> : null}

      {stats.data ? <StatCards data={stats.data} /> : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {recentRuns.data ? <RecentRunsTable data={recentRuns.data} /> : null}
        </div>
        <div>
          {defectSummary.data ? (
            <DefectSeverityPanel data={defectSummary.data} />
          ) : null}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {stats.data ? <RunsByOutcomePanel data={stats.data} /> : null}
        {defectSummary.data ? <DefectTypePanel data={defectSummary.data} /> : null}
      </div>
    </div>
  );
}

function StatCards({ data }: { data: DashboardStats }) {
  const cards = [
    {
      label: "Total WADs",
      value: data.total_wads,
      icon: <FolderArchive className="h-4 w-4" />,
      color: "text-blue-600",
      bg: "bg-blue-50",
    },
    {
      label: "Total Runs",
      value: data.total_runs,
      icon: <Play className="h-4 w-4" />,
      color: "text-emerald-600",
      bg: "bg-emerald-50",
    },
    {
      label: "Total Defects",
      value: data.total_defects,
      icon: <AlertTriangle className="h-4 w-4" />,
      color: "text-amber-600",
      bg: "bg-amber-50",
    },
    {
      label: "Avg Coverage",
      value: data.avg_coverage_pct != null ? `${data.avg_coverage_pct}%` : "—",
      icon: <Target className="h-4 w-4" />,
      color:
        data.avg_coverage_pct != null
          ? data.avg_coverage_pct >= 60
            ? "text-emerald-600"
            : data.avg_coverage_pct >= 40
              ? "text-amber-600"
              : "text-red-600"
          : "text-neutral-400",
      bg:
        data.avg_coverage_pct != null
          ? data.avg_coverage_pct >= 60
            ? "bg-emerald-50"
            : data.avg_coverage_pct >= 40
              ? "bg-amber-50"
              : "bg-red-50"
          : "bg-neutral-50",
    },
    {
      label: "Avg Kill Rate",
      value: data.avg_kill_rate_pct != null ? `${data.avg_kill_rate_pct}%` : "—",
      icon: <Crosshair className="h-4 w-4" />,
      color:
        data.avg_kill_rate_pct != null
          ? data.avg_kill_rate_pct >= 50
            ? "text-emerald-600"
            : data.avg_kill_rate_pct >= 30
              ? "text-amber-600"
              : "text-red-600"
          : "text-neutral-400",
      bg:
        data.avg_kill_rate_pct != null
          ? data.avg_kill_rate_pct >= 50
            ? "bg-emerald-50"
            : data.avg_kill_rate_pct >= 30
              ? "bg-amber-50"
              : "bg-red-50"
          : "bg-neutral-50",
    },
    {
      label: "Total LLM Cost",
      value: `$${data.total_llm_cost_usd.toFixed(2)}`,
      icon: <DollarSign className="h-4 w-4" />,
      color: "text-violet-600",
      bg: "bg-violet-50",
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded border border-neutral-200 bg-white p-4"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase text-neutral-500">
              {card.label}
            </span>
            <span className={`rounded-full p-1.5 ${card.bg} ${card.color}`}>
              {card.icon}
            </span>
          </div>
          <p className="mt-2 text-2xl font-bold text-neutral-950">{card.value}</p>
        </div>
      ))}
    </div>
  );
}

function RecentRunsTable({ data }: { data: DashboardRecentRun[] }) {
  const router = useRouter();
  if (data.length === 0) {
    return (
      <div className="rounded border border-neutral-200 bg-white p-6 text-center text-sm text-neutral-500">
        No runs yet. Upload a WAD and start a run to see results here.
      </div>
    );
  }
  return (
    <div className="rounded border border-neutral-200 bg-white">
      <div className="border-b border-neutral-200 px-4 py-3">
        <h3 className="text-sm font-semibold">Recent Runs</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-neutral-100 text-xs uppercase text-neutral-500">
              <th className="px-4 py-2">Map</th>
              <th className="px-4 py-2">WAD</th>
              <th className="px-4 py-2">Outcome</th>
              <th className="px-4 py-2 text-right">Diff</th>
              <th className="px-4 py-2 text-right">Coverage</th>
              <th className="px-4 py-2 text-right">Kills</th>
              <th className="px-4 py-2 text-right">Defects</th>
              <th className="px-4 py-2 text-right">Duration</th>
              <th className="px-4 py-2 text-right">Cost</th>
              <th className="px-4 py-2 text-right">Created</th>
            </tr>
          </thead>
          <tbody>
            {data.map((run) => (
              <tr
                key={run.id}
                onClick={() => router.push(`/run/${run.id}`)}
                className="cursor-pointer border-b border-neutral-50 hover:bg-neutral-50"
              >
                <td className="px-4 py-2 font-medium text-neutral-950">
                  {run.map_name}
                </td>
                <td className="max-w-[120px] truncate px-4 py-2 text-neutral-600">
                  {run.wad_filename}
                </td>
                <td className="px-4 py-2">
                  <OutcomeBadge outcome={run.outcome} />
                </td>
                <td className="px-4 py-2 text-right text-neutral-600">
                  {run.difficulty_level ?? "—"}
                </td>
                <td className="px-4 py-2 text-right">
                  <CoverageBar value={run.coverage_pct} />
                </td>
                <td className="px-4 py-2 text-right text-neutral-600">
                  {run.total_kills != null && run.spawned_enemies != null
                    ? `${run.total_kills}/${run.spawned_enemies}`
                    : run.total_kills ?? "—"}
                </td>
                <td className="px-4 py-2 text-right">
                  <span
                    className={
                      run.defect_count > 0
                        ? "font-semibold text-amber-600"
                        : "text-neutral-400"
                    }
                  >
                    {run.defect_count}
                  </span>
                </td>
                <td className="px-4 py-2 text-right text-neutral-600">
                  {run.duration_seconds != null
                    ? `${Math.round(run.duration_seconds)}s`
                    : "—"}
                </td>
                <td className="px-4 py-2 text-right text-neutral-600">
                  ${run.llm_cost_usd.toFixed(3)}
                </td>
                <td className="px-4 py-2 text-right text-neutral-500">
                  {run.created_at
                    ? formatTime(new Date(run.created_at).getTime())
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CoverageBar({ value }: { value: number | null }) {
  if (value == null) return <span className="text-neutral-400">—</span>;
  const color =
    value >= 60 ? "bg-emerald-500" : value >= 40 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-neutral-100">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${Math.min(value, 100)}%` }}
        />
      </div>
      <span className="text-xs text-neutral-600">{value}%</span>
    </div>
  );
}

function DefectSeverityPanel({ data }: { data: DashboardDefectSummary }) {
  const maxCount = Math.max(...data.by_severity.map((s) => s.count), 1);
  const severityLabels: Record<number, { label: string; color: string }> = {
    1: { label: "Critical", color: "bg-red-500" },
    2: { label: "Major", color: "bg-amber-500" },
    3: { label: "Minor", color: "bg-blue-500" },
    4: { label: "Cosmetic", color: "bg-neutral-400" },
  };
  return (
    <div className="rounded border border-neutral-200 bg-white p-4">
      <h3 className="mb-3 text-sm font-semibold">Defects by Severity</h3>
      {data.by_severity.length === 0 ? (
        <p className="text-xs text-neutral-500">No defects recorded</p>
      ) : (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((sev) => {
            const entry = data.by_severity.find((s) => s.severity === sev);
            const count = entry?.count ?? 0;
            const meta = severityLabels[sev] ?? { label: `S${sev}`, color: "bg-neutral-400" };
            return (
              <div key={sev}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="font-medium text-neutral-700">{meta.label}</span>
                  <span className="text-neutral-500">{count}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-neutral-100">
                  <div
                    className={`h-full rounded-full ${meta.color}`}
                    style={{ width: `${(count / maxCount) * 100}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function RunsByOutcomePanel({ data }: { data: DashboardStats }) {
  const entries = Object.entries(data.runs_by_outcome).sort((a, b) => b[1] - a[1]);
  const maxCount = Math.max(...entries.map((e) => e[1]), 1);
  const outcomeColors: Record<string, string> = {
    map_completed: "bg-emerald-500",
    player_died: "bg-red-500",
    inconclusive_agent_stall: "bg-amber-500",
    error: "bg-red-600",
    pwad_crash: "bg-red-700",
    unknown: "bg-neutral-400",
  };
  return (
    <div className="rounded border border-neutral-200 bg-white p-4">
      <h3 className="mb-3 text-sm font-semibold">Runs by Outcome</h3>
      {entries.length === 0 ? (
        <p className="text-xs text-neutral-500">No runs yet</p>
      ) : (
        <div className="space-y-2">
          {entries.map(([outcome, count]) => (
            <div key={outcome}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="font-medium text-neutral-700">
                  {outcome.replace(/_/g, " ")}
                </span>
                <span className="text-neutral-500">{count}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-neutral-100">
                <div
                  className={`h-full rounded-full ${outcomeColors[outcome] ?? "bg-neutral-400"}`}
                  style={{ width: `${(count / maxCount) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DefectTypePanel({ data }: { data: DashboardDefectSummary }) {
  const sorted = [...data.by_type].sort((a, b) => b.count - a.count);
  const maxCount = Math.max(...sorted.map((s) => s.count), 1);
  return (
    <div className="rounded border border-neutral-200 bg-white p-4">
      <h3 className="mb-3 text-sm font-semibold">Defects by Type</h3>
      {sorted.length === 0 ? (
        <p className="text-xs text-neutral-500">No defects recorded</p>
      ) : (
        <div className="space-y-2">
          {sorted.map((entry) => (
            <div key={entry.defect_type}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="font-medium text-neutral-700">
                  {entry.defect_type.replace(/_/g, " ")}
                </span>
                <span className="text-neutral-500">
                  {entry.count} (avg sev: {entry.avg_severity})
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-neutral-100">
                <div
                  className="h-full rounded-full bg-violet-500"
                  style={{ width: `${(entry.count / maxCount) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
