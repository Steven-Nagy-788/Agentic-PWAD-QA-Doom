"use client";

import { useMemo } from "react";

interface AsciiGridProps {
  grid: string | null | undefined;
  className?: string;
}

const CHARACTER_COLORS: Record<string, string> = {
  P: "text-cyan-600 font-bold",
  E: "text-red-600 font-bold",
  I: "text-green-600",
  W: "text-blue-600 font-bold",
  K: "text-yellow-500 font-bold",
  D: "text-purple-600",
  "?": "text-neutral-400",
  "#": "text-neutral-300",
  ".": "text-neutral-600",
};

export function AsciiGrid({ grid, className }: AsciiGridProps) {
  const lines = useMemo(() => {
    if (!grid) return [];
    return grid.split("\n");
  }, [grid]);

  if (!grid) {
    return (
      <div className={`grid place-items-center text-xs text-neutral-400 ${className ?? ""}`}>
        No grid data available
      </div>
    );
  }

  const headerLines: string[] = [];
  const gridLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("Player") || line.startsWith("Legend")) {
      headerLines.push(line);
    } else {
      gridLines.push(line);
    }
  }

  return (
    <div className={`overflow-auto font-mono text-[10px] leading-tight ${className ?? ""}`}>
      <div className="mb-1 space-y-0.5 text-neutral-500">
        {headerLines.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>
      <pre className="inline-block bg-neutral-900 p-2 text-neutral-100">
        {gridLines.map((line, lineIdx) => (
          <div key={lineIdx}>
            {Array.from(line).map((char, charIdx) => (
              <span key={charIdx} className={CHARACTER_COLORS[char] ?? ""}>
                {char}
              </span>
            ))}
          </div>
        ))}
      </pre>
      <div className="mt-1 text-[9px] text-neutral-500">
        Legend: <span className="text-red-600">E</span>=enemy{" "}
        <span className="text-green-600">I</span>=item{" "}
        <span className="text-blue-600">W</span>=weapon{" "}
        <span className="text-yellow-500">K</span>=key{" "}
        <span className="text-purple-600">D</span>=door{" "}
        <span className="text-cyan-600">P</span>=player{" "}
        <span className="text-neutral-400">?</span>=unexplored
      </div>
    </div>
  );
}
