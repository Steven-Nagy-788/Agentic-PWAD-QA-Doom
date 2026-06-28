"use client";

import type React from "react";
import { LayoutDashboard, FileArchive, History, HeartPulse, Cog } from "lucide-react";
import { usePathname } from "next/navigation";
import Link from "next/link";

export function NavBar() {
  const pathname = usePathname();
  const nav = [
    { href: "/dashboard", icon: <LayoutDashboard />, label: "Dashboard", active: pathname === "/dashboard" },
    { href: "/", icon: <FileArchive />, label: "WADs", active: pathname === "/" || pathname.startsWith("/wad/") },
    { href: "/history", icon: <History />, label: "Runs", active: pathname.startsWith("/history") || pathname.startsWith("/run/") },
    { href: "/health", icon: <HeartPulse />, label: "Health", active: pathname.startsWith("/health") },
    { href: "/settings", icon: <Cog />, label: "Settings", active: pathname.startsWith("/settings") },
  ];
  return (
    <aside className="border-b border-neutral-200 bg-white md:border-b-0 md:border-r">
      <div className="flex items-center gap-3 border-b border-neutral-200 p-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.png" alt="BoJack" className="h-9 w-9 rounded-full" />
        <h1 className="text-lg font-semibold tracking-normal">BoJack</h1>
      </div>
      <nav className="grid grid-cols-3 gap-1 p-3 md:grid-cols-1">
        {nav.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex h-10 items-center gap-2 rounded px-3 text-sm font-semibold ${item.active ? "bg-neutral-950 text-white" : "text-neutral-700 hover:bg-neutral-100"}`}
          >
            <span className="[&>svg]:h-4 [&>svg]:w-4">{item.icon}</span>
            {item.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}

export function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded border border-neutral-200 bg-neutral-50 px-3 py-2">
      <span className="block text-[11px] font-medium uppercase text-neutral-500">{label}</span>
      <span className="block truncate text-sm font-semibold text-neutral-950">{value}</span>
    </div>
  );
}

export function OutcomeBadge({ outcome }: { outcome?: string | null }) {
  const value = outcome ?? "unknown";
  const tone = value === "map_completed" || value === "ok" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : value === "pwad_crash" || value === "error" ? "border-red-200 bg-red-50 text-red-800" : "border-amber-200 bg-amber-50 text-amber-900";
  return <span className={`inline-flex rounded border px-2.5 py-1 text-xs font-semibold ${tone}`}>{value}</span>;
}

export function InlineError({ message }: { message: string }) {
  return <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{message}</div>;
}

export function EmptyState({ title }: { title: string }) {
  return <div className="grid min-h-[50vh] place-items-center text-sm text-neutral-500">{title}</div>;
}

export function SkeletonRows() {
  return (
    <div className="space-y-2">
      {[0, 1, 2].map((item) => (
        <div key={item} className="h-20 animate-pulse rounded border border-neutral-200 bg-white" />
      ))}
    </div>
  );
}

export function errorMessage(error: unknown): string | undefined {
  return error instanceof Error ? error.message : undefined;
}

export function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatTime(ts: number) {
  const seconds = Math.floor((Date.now() - ts) / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ago`;
}
