import { Activity, Crosshair, Gauge, Shield, Zap } from "lucide-react";
import type React from "react";

export type StatBarState = {
  tick?: number;
  health?: number;
  armor?: number;
  kills?: number;
  secrets?: number;
  ammo?: { bullets?: number; shells?: number; rockets?: number; cells?: number };
};

export function StatBar({ state }: { state?: StatBarState | null }) {
  const ammo =
    (state?.ammo?.bullets ?? 0) +
    (state?.ammo?.shells ?? 0) +
    (state?.ammo?.rockets ?? 0) +
    (state?.ammo?.cells ?? 0);
  return (
    <div className="grid grid-cols-3 gap-2 border-t border-neutral-200 bg-white p-3 text-sm md:grid-cols-6">
      <Stat icon={<Activity />} label="HP" value={state?.health ?? 0} />
      <Stat icon={<Shield />} label="Armor" value={state?.armor ?? 0} />
      <Stat icon={<Zap />} label="Ammo" value={ammo} />
      <Stat icon={<Crosshair />} label="Kills" value={state?.kills ?? 0} />
      <Stat icon={<Gauge />} label="Secrets" value={state?.secrets ?? 0} />
      <Stat icon={<Gauge />} label="Tick" value={state?.tick ?? 0} />
    </div>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactElement; label: string; value: number }) {
  return (
    <div className="flex min-h-12 items-center gap-2 rounded border border-neutral-200 bg-neutral-50 px-3">
      <span className="text-neutral-500 [&>svg]:h-4 [&>svg]:w-4">{icon}</span>
      <span className="min-w-0">
        <span className="block text-[11px] font-medium uppercase text-neutral-500">{label}</span>
        <span className="block truncate font-semibold text-neutral-950">{value}</span>
      </span>
    </div>
  );
}
