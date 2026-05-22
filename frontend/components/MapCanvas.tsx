"use client";

/* eslint-disable @next/next/no-img-element */

import { assetUrl, PositionSample, TraceEntry, WadMap } from "@/lib/api";

type MapCanvasProps = {
  map?: WadMap | null;
  trail?: PositionSample[];
  events?: TraceEntry[];
  livePosition?: { x: number; y: number } | null;
  className?: string;
};

export function MapCanvas({ map, trail = [], events = [], livePosition, className = "" }: MapCanvasProps) {
  const imageUrl = assetUrl(map?.map_overview_png_url);
  const points = livePosition ? [...trail, { id: -1, run_id: "", tick_number: 0, x: livePosition.x, y: livePosition.y, health: 0 }] : trail;
  const bounds = getBounds(points);
  return (
    <div className={`relative aspect-square overflow-hidden rounded border border-neutral-200 bg-neutral-950 ${className}`}>
      {imageUrl ? (
        <img src={imageUrl} alt={`${map?.map_name ?? "Map"} overview`} className="absolute inset-0 h-full w-full object-cover opacity-80" />
      ) : (
        <div className="absolute inset-0 bg-[linear-gradient(90deg,#262626_1px,transparent_1px),linear-gradient(#262626_1px,transparent_1px)] bg-[size:32px_32px]" />
      )}
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1000 1000" aria-hidden="true">
        {trail.map((sample, index) => {
          const p = project(sample.x, sample.y, bounds);
          return <circle key={`${sample.tick_number}-${index}`} cx={p.x} cy={p.y} r="5" fill="rgba(59,130,246,0.62)" />;
        })}
        {events.map((event) => {
          const p = project(event.player_x, event.player_y, bounds);
          const color = event.event_type === "kill" ? "#dc2626" : event.event_type === "item_pickup" ? "#16a34a" : "#f59e0b";
          if (event.event_type === "death") {
            return (
              <g key={event.id} stroke="#0a0a0a" strokeWidth="8">
                <line x1={p.x - 12} y1={p.y - 12} x2={p.x + 12} y2={p.y + 12} />
                <line x1={p.x + 12} y1={p.y - 12} x2={p.x - 12} y2={p.y + 12} />
              </g>
            );
          }
          return <circle key={event.id} cx={p.x} cy={p.y} r="9" fill={color} stroke="white" strokeWidth="3" />;
        })}
        {livePosition ? (
          <circle
            cx={project(livePosition.x, livePosition.y, bounds).x}
            cy={project(livePosition.x, livePosition.y, bounds).y}
            r="13"
            fill="#0891b2"
            stroke="white"
            strokeWidth="4"
          />
        ) : null}
      </svg>
    </div>
  );
}

function getBounds(points: { x: number; y: number }[]) {
  if (!points.length) {
    return { minX: -1, maxX: 1, minY: -1, maxY: 1 };
  }
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  return {
    minX: minX === maxX ? minX - 1 : minX,
    maxX: minX === maxX ? maxX + 1 : maxX,
    minY: minY === maxY ? minY - 1 : minY,
    maxY: minY === maxY ? maxY + 1 : maxY,
  };
}

function project(x: number, y: number, bounds: ReturnType<typeof getBounds>) {
  const px = 50 + ((x - bounds.minX) / (bounds.maxX - bounds.minX)) * 900;
  const py = 950 - ((y - bounds.minY) / (bounds.maxY - bounds.minY)) * 900;
  return { x: px, y: py };
}
