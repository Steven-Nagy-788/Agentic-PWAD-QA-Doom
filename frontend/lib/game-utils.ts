import type { Defect, PositionSample, Run, RunList } from "@/lib/api";
import type { SameRunMemory } from "@/hooks/useRunStream";

export function isCosmeticTextureDefect(defect: Defect) {
  const type = (defect.defect_type ?? "").toLowerCase();
  const text = `${type} ${defect.title ?? ""} ${defect.description ?? ""}`.toLowerCase();
  if (text.includes("hom") || text.includes("hall of mirrors") || text.includes("missing texture") || text.includes("medusa")) {
    return false;
  }
  if (type === "visual_texture_misalignment") {
    return true;
  }
  const issue = ["alignment", "misalign", "offset", "tiling", "discontinuity", "repeat", "cut-off", "cut off", "seam"].some((term) => text.includes(term));
  const surface = ["texture", "floor", "wall", "pillar"].some((term) => text.includes(term));
  return issue && surface;
}

export function liveTrail(memory: SameRunMemory | null, snapshotTrail: PositionSample[]): PositionSample[] {
  const positions = memory?.recent_actions
    .map((action) => ({ ...action.final_position, tick: action.tick_after }))
    .filter((sample) => sample.x !== undefined && sample.y !== undefined) ?? [];
  const latestHealth = snapshotTrail.at(-1)?.health ?? 0;
  const merged = new Map(snapshotTrail.map((sample) => [`${sample.tick_number}:${sample.x}:${sample.y}`, sample]));
  positions.forEach((sample, index) => {
    const entry = {
      id: -(index + 1),
      run_id: "",
      tick_number: sample.tick,
      x: sample.x ?? 0,
      y: sample.y ?? 0,
      angle: sample.angle ?? 0,
      health: latestHealth,
    };
    merged.set(`${entry.tick_number}:${entry.x}:${entry.y}`, entry);
  });
  return Array.from(merged.values()).sort((a, b) => a.tick_number - b.tick_number);
}

export function normalizeRunList(data: RunList | Run[]): RunList {
  return Array.isArray(data) ? { total: data.length, items: data, offset: 0 } : data;
}

export function sparklinePath(values: number[], width = 128, height = 36) {
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
