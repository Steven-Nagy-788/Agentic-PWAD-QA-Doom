import { SkillSummary } from "@/lib/api";

export function SkillHeatmap({ summary }: { summary?: Record<string, SkillSummary> | null }) {
  const values = [1, 2, 3, 4, 5].map((skill) => {
    const row = summary?.[String(skill)];
    return { skill, enemies: row?.thing_count_enemies ?? 0 };
  });
  const max = Math.max(1, ...values.map((item) => item.enemies));
  return (
    <div className="grid grid-cols-5 overflow-hidden rounded border border-neutral-200">
      {values.map((item) => (
        <div
          key={item.skill}
          className="flex h-9 flex-col items-center justify-center border-r border-neutral-200 text-[11px] last:border-r-0"
          style={{ backgroundColor: heatColor(item.enemies / max) }}
          title={`Skill ${item.skill}: ${item.enemies} enemies`}
        >
          <span className="font-semibold text-neutral-950">{item.skill}</span>
          <span className="text-neutral-700">{item.enemies}</span>
        </div>
      ))}
    </div>
  );
}

function heatColor(value: number) {
  const clamped = Math.max(0, Math.min(1, value));
  const red = Math.round(245 - clamped * 15);
  const green = Math.round(247 - clamped * 120);
  const blue = Math.round(238 - clamped * 165);
  return `rgb(${red}, ${green}, ${blue})`;
}
