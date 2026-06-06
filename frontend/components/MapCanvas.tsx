"use client";

/* eslint-disable @next/next/no-img-element */

import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { assetUrl, PositionSample, TraceEntry, WadMap } from "@/lib/api";

type MapCanvasProps = {
  map?: WadMap | null;
  trail?: PositionSample[];
  events?: TraceEntry[];
  livePosition?: { x: number; y: number } | null;
  visitedCells?: Record<string, number>;
  visitedCellSize?: number;
  fit?: "square" | "contain";
  className?: string;
};

const STEP = 15;
const VIEW_SIZE = 1024;
const MAP_MARGIN = 20;

export function MapCanvas({ map, trail = [], events = [], livePosition, visitedCells = {}, visitedCellSize = 256, fit = "square", className = "" }: MapCanvasProps) {
  const imageUrl = assetUrl(map?.map_overview_png_url);
  const points = livePosition ? [...trail, { id: -1, run_id: "", tick_number: 0, x: livePosition.x, y: livePosition.y, health: 0 }] : trail;
  const bounds = getBounds(points, map);
  const [focusX, setFocusX] = useState(VIEW_SIZE / 2);
  const [focusY, setFocusY] = useState(VIEW_SIZE / 2);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [containedSize, setContainedSize] = useState<number | null>(null);

  useEffect(() => {
    if (fit !== "contain") {
      return;
    }
    const viewport = viewportRef.current;
    if (!viewport) {
      return;
    }
    const measure = () => {
      const rect = viewport.getBoundingClientRect();
      const next = Math.floor(Math.min(rect.width, rect.height));
      setContainedSize(next > 0 ? next : null);
    };
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [fit]);

  const onKeyDown = useCallback((event: React.KeyboardEvent<SVGSVGElement>) => {
    switch (event.key) {
      case "ArrowUp":
        event.preventDefault();
        setFocusY((prev) => Math.max(0, prev - STEP));
        break;
      case "ArrowDown":
        event.preventDefault();
        setFocusY((prev) => Math.min(VIEW_SIZE, prev + STEP));
        break;
      case "ArrowLeft":
        event.preventDefault();
        setFocusX((prev) => Math.max(0, prev - STEP));
        break;
      case "ArrowRight":
        event.preventDefault();
        setFocusX((prev) => Math.min(VIEW_SIZE, prev + STEP));
        break;
    }
  }, []);

  const mapLayer = (
    <>
      {imageUrl ? (
        <img src={imageUrl} alt={`${map?.map_name ?? "Map"} overview`} className="absolute inset-0 h-full w-full object-contain opacity-80" />
      ) : (
        <div className="absolute inset-0 bg-[linear-gradient(90deg,#262626_1px,transparent_1px),linear-gradient(#262626_1px,transparent_1px)] bg-[size:32px_32px]" />
      )}
      <span className="sr-only">Map overview with player position trail</span>
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox={`0 0 ${VIEW_SIZE} ${VIEW_SIZE}`}
        preserveAspectRatio="xMidYMid meet"
        tabIndex={0}
        role="application"
        aria-label={`${map?.map_name ?? "Map"} overview with player position trail. Use arrow keys to navigate.`}
        onKeyDown={onKeyDown}
      >
        {Object.entries(visitedCells).map(([key, count]) => {
          const [cx, cy] = key.split(",").map(Number);
          if (!Number.isFinite(cx) || !Number.isFinite(cy)) {
            return null;
          }
          const worldX = cx * visitedCellSize;
          const worldY = cy * visitedCellSize;
          const halfCell = visitedCellSize / 2;
          const topLeft = project(worldX - halfCell, worldY + halfCell, bounds);
          const bottomRight = project(worldX + halfCell, worldY - halfCell, bounds);
          const opacity = Math.min(0.4, 0.1 + count * 0.05);
          return (
            <rect
              key={key}
              x={Math.min(topLeft.x, bottomRight.x)}
              y={Math.min(topLeft.y, bottomRight.y)}
              width={Math.max(Math.abs(bottomRight.x - topLeft.x), 2)}
              height={Math.max(Math.abs(bottomRight.y - topLeft.y), 2)}
              fill="#22c55e"
              fillOpacity={opacity}
              stroke="none"
            />
          );
        })}
        {points.length > 1 ? (
          <polyline
            points={points.map((sample) => {
              const p = project(sample.x, sample.y, bounds);
              return `${p.x},${p.y}`;
            }).join(" ")}
            fill="none"
            stroke="#2563eb"
            strokeWidth="7"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity="0.78"
          />
        ) : null}
        {trail.map((sample, index) => {
          const p = project(sample.x, sample.y, bounds);
          return <circle key={`${sample.tick_number}-${index}`} cx={p.x} cy={p.y} r="5" fill="rgba(59,130,246,0.62)" />;
        })}
        {trail.length ? (
          <>
            <circle cx={project(trail[0].x, trail[0].y, bounds).x} cy={project(trail[0].x, trail[0].y, bounds).y} r="11" fill="#16a34a" stroke="white" strokeWidth="3" />
            <circle
              cx={project(trail[trail.length - 1].x, trail[trail.length - 1].y, bounds).x}
              cy={project(trail[trail.length - 1].x, trail[trail.length - 1].y, bounds).y}
              r="12"
              fill="#f59e0b"
              stroke="white"
              strokeWidth="3"
            />
          </>
        ) : null}
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
        <circle cx={focusX} cy={focusY} r="14" fill="none" stroke="white" strokeWidth="3" className="drop-shadow-lg" />
        <circle cx={focusX} cy={focusY} r="14" fill="none" stroke="#0891b2" strokeWidth="1.5" />
      </svg>
    </>
  );

  if (fit === "contain") {
    const frameStyle: CSSProperties | undefined = containedSize
      ? { width: containedSize, height: containedSize }
      : { aspectRatio: "1 / 1", maxHeight: "100%", maxWidth: "100%", width: "100%" };
    return (
      <div ref={viewportRef} data-testid="map-canvas-viewport" className={`grid min-h-0 w-full place-items-center overflow-hidden ${className}`}>
        <div data-testid="map-canvas-frame" className="relative overflow-hidden rounded border border-neutral-200 bg-neutral-950" style={frameStyle}>
          {mapLayer}
        </div>
      </div>
    );
  }

  return (
    <div data-testid="map-canvas-frame" className={`relative aspect-square overflow-hidden rounded border border-neutral-200 bg-neutral-950 ${className}`}>
      {mapLayer}
    </div>
  );
}

function getBounds(points: { x: number; y: number }[], map?: WadMap | null) {
  const mapBounds = mapBoundsFromMetadata(map);
  if (mapBounds) {
    return mapBounds;
  }
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

function mapBoundsFromMetadata(map?: WadMap | null) {
  const minX = numberOrNull(map?.map_min_x);
  const maxX = numberOrNull(map?.map_max_x);
  const minY = numberOrNull(map?.map_min_y);
  const maxY = numberOrNull(map?.map_max_y);
  if (minX == null || maxX == null || minY == null || maxY == null || minX === maxX || minY === maxY) {
    return null;
  }
  return { minX, maxX, minY, maxY };
}

function numberOrNull(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function project(x: number, y: number, bounds: ReturnType<typeof getBounds>) {
  const drawable = VIEW_SIZE - MAP_MARGIN * 2;
  const px = MAP_MARGIN + ((x - bounds.minX) / (bounds.maxX - bounds.minX)) * drawable;
  const py = VIEW_SIZE - MAP_MARGIN - ((y - bounds.minY) / (bounds.maxY - bounds.minY)) * drawable;
  return { x: px, y: py };
}
