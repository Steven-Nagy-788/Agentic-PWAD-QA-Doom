import { describe, it, expect } from "vitest";
import type { Defect, PositionSample, Run, RunList } from "@/lib/api";
import type { SameRunMemory } from "@/hooks/useRunStream";
import {
  isCosmeticTextureDefect,
  liveTrail,
  normalizeRunList,
  sparklinePath,
} from "../game-utils";

describe("isCosmeticTextureDefect", () => {
  it("returns false for HOM defects", () => {
    const defect: Defect = { defect_type: "hom", title: "Hall of mirrors", description: null } as Defect;
    expect(isCosmeticTextureDefect(defect)).toBe(false);
  });

  it("returns false for missing texture", () => {
    const defect: Defect = { defect_type: "missing_texture", title: null, description: null } as Defect;
    expect(isCosmeticTextureDefect(defect)).toBe(false);
  });

  it("returns false for medusa", () => {
    const defect: Defect = { defect_type: null, title: null, description: "medusa effect" } as Defect;
    expect(isCosmeticTextureDefect(defect)).toBe(false);
  });

  it("returns true for visual_texture_misalignment type", () => {
    const defect: Defect = { defect_type: "visual_texture_misalignment", title: null, description: null } as Defect;
    expect(isCosmeticTextureDefect(defect)).toBe(true);
  });

  it("returns true for texture alignment text", () => {
    const defect: Defect = { defect_type: "other", title: "texture alignment", description: null } as Defect;
    expect(isCosmeticTextureDefect(defect)).toBe(true);
  });

  it("returns true for wall seam text", () => {
    const defect: Defect = { defect_type: "other", title: "wall seam", description: null } as Defect;
    expect(isCosmeticTextureDefect(defect)).toBe(true);
  });

  it("returns true for floor tiling text", () => {
    const defect: Defect = { defect_type: "other", title: "floor tiling issue", description: null } as Defect;
    expect(isCosmeticTextureDefect(defect)).toBe(true);
  });

  it("returns true for pillar offset text", () => {
    const defect: Defect = { defect_type: "other", title: null, description: "pillar offset visible" } as Defect;
    expect(isCosmeticTextureDefect(defect)).toBe(true);
  });

  it("returns true for visual_stuck_monster with alignment in description (no HOM/medusa)", () => {
    const defect: Defect = {
      defect_type: "visual_stuck_monster",
      title: "monster stuck",
      description: "alignment issue near wall",
    } as Defect;
    expect(isCosmeticTextureDefect(defect)).toBe(true);
  });

  it("returns false for empty defect", () => {
    expect(isCosmeticTextureDefect({} as Defect)).toBe(false);
  });

  it("returns false for normal defect with no texture terms", () => {
    const defect: Defect = {
      defect_type: "gameplay",
      title: "enemy too strong",
      description: null,
    } as Defect;
    expect(isCosmeticTextureDefect(defect)).toBe(false);
  });
});

describe("liveTrail", () => {
  it("returns snapshotTrail sorted when memory is null", () => {
    const snapshot: PositionSample[] = [
      { tick_number: 3, x: 10, y: 20, health: 50, id: 1, run_id: "r1" },
      { tick_number: 1, x: 5, y: 5, health: 80, id: 2, run_id: "r1" },
    ];
    const result = liveTrail(null, snapshot);
    expect(result[0].tick_number).toBe(1);
    expect(result[1].tick_number).toBe(3);
  });

  it("returns memory positions when snapshotTrail is empty", () => {
    const memory: SameRunMemory = {
      recent_actions: [
        { final_position: { x: 100, y: 200 }, tick_after: 5 } as SameRunMemory["recent_actions"][0],
        { final_position: { x: 50, y: 60 }, tick_after: 2 } as SameRunMemory["recent_actions"][0],
      ],
    };
    const result = liveTrail(memory, []);
    expect(result).toHaveLength(2);
    expect(result[0].tick_number).toBe(2);
    expect(result[1].tick_number).toBe(5);
  });

  it("deduplicates by tick:x:y key", () => {
    const memory: SameRunMemory = {
      recent_actions: [
        { final_position: { x: 10, y: 20 }, tick_after: 1 } as SameRunMemory["recent_actions"][0],
      ],
    };
    const snapshot: PositionSample[] = [
      { tick_number: 1, x: 10, y: 20, health: 50, id: 1, run_id: "r1" },
    ];
    const result = liveTrail(memory, snapshot);
    expect(result).toHaveLength(1);
  });

  it("sorts merged result by tick_number ascending", () => {
    const memory: SameRunMemory = {
      recent_actions: [
        { final_position: { x: 100, y: 200 }, tick_after: 10 } as SameRunMemory["recent_actions"][0],
        { final_position: { x: 50, y: 60 }, tick_after: 2 } as SameRunMemory["recent_actions"][0],
      ],
    };
    const snapshot: PositionSample[] = [
      { tick_number: 5, x: 30, y: 40, health: 70, id: 1, run_id: "r1" },
    ];
    const result = liveTrail(memory, snapshot);
    expect(result.map((p) => p.tick_number)).toEqual([2, 5, 10]);
  });
});

describe("normalizeRunList", () => {
  it("wraps array input in { total, items, offset }", () => {
    const runs: Run[] = [{ id: "1" } as Run, { id: "2" } as Run];
    const result = normalizeRunList(runs);
    expect(result).toEqual({ total: 2, items: runs, offset: 0 });
  });

  it("passes through object with items unchanged", () => {
    const list: RunList = { total: 5, items: [{ id: "3" } as Run], offset: 10 };
    const result = normalizeRunList(list);
    expect(result).toBe(list);
  });
});

describe("sparklinePath", () => {
  it("returns empty string for empty values", () => {
    expect(sparklinePath([])).toBe("");
  });

  it("returns single M command for single value", () => {
    const path = sparklinePath([50]);
    expect(path.startsWith("M")).toBe(true);
    expect(path).not.toContain("L");
  });

  it("returns M + L commands for multiple values", () => {
    const path = sparklinePath([10, 20, 30]);
    expect(path).toContain("M");
    expect(path).toContain("L");
    const parts = path.split(" ");
    expect(parts).toHaveLength(3);
  });

  it("maps min value to bottom y and max value to top y", () => {
    const path = sparklinePath([0, 100], 100, 50);
    const points = path.split(" ");
    const yValues = points.map((p) => parseFloat(p.split(",")[1]));
    expect(yValues[0]).toBeGreaterThan(yValues[1]);
  });
});
