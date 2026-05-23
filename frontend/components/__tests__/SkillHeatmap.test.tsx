import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SkillHeatmap } from "../SkillHeatmap";

describe("SkillHeatmap", () => {
  it("renders 5 cells with correct enemy counts", () => {
    const summary = {
      "1": { thing_count_enemies: 10, difficulty_level: 1, thing_count_items: 5, total_health_pickup_pts: 20, ammo_ratio: 1.5, health_ratio: 2.0, estimated_difficulty: "easy" },
      "2": { thing_count_enemies: 15, difficulty_level: 2, thing_count_items: 5, total_health_pickup_pts: 20, ammo_ratio: 1.5, health_ratio: 2.0, estimated_difficulty: "easy" },
      "3": { thing_count_enemies: 20, difficulty_level: 3, thing_count_items: 5, total_health_pickup_pts: 20, ammo_ratio: 1.5, health_ratio: 2.0, estimated_difficulty: "medium" },
      "4": { thing_count_enemies: 25, difficulty_level: 4, thing_count_items: 5, total_health_pickup_pts: 20, ammo_ratio: 1.5, health_ratio: 2.0, estimated_difficulty: "hard" },
      "5": { thing_count_enemies: 30, difficulty_level: 5, thing_count_items: 5, total_health_pickup_pts: 20, ammo_ratio: 1.5, health_ratio: 2.0, estimated_difficulty: "very hard" },
    };

    render(<SkillHeatmap summary={summary} />);

    const container = screen.getByRole("img", { name: /enemy count by skill level/i });
    expect(container).toBeInTheDocument();

    const cells = container.querySelectorAll("[tabindex]");
    expect(cells).toHaveLength(5);

    expect(cells[0]).toHaveAttribute("title", "Skill 1: 10 enemies");
    expect(cells[1]).toHaveAttribute("title", "Skill 2: 15 enemies");
    expect(cells[2]).toHaveAttribute("title", "Skill 3: 20 enemies");
    expect(cells[3]).toHaveAttribute("title", "Skill 4: 25 enemies");
    expect(cells[4]).toHaveAttribute("title", "Skill 5: 30 enemies");
  });

  it("shows loading state when no summary provided", () => {
    render(<SkillHeatmap />);

    const container = screen.getByRole("img", { name: /enemy count by skill level loading/i });
    expect(container).toBeInTheDocument();
    expect(container.querySelectorAll("[class*=animate-pulse]")).toHaveLength(5);
  });

  it("handles empty summary gracefully", () => {
    render(<SkillHeatmap summary={{}} />);

    const container = screen.getByRole("img", { name: /enemy count by skill level/i });
    expect(container).toBeInTheDocument();

    const cells = container.querySelectorAll("[tabindex]");
    expect(cells).toHaveLength(5);
    cells.forEach((cell) => {
      expect(cell.textContent).toContain("0");
    });
  });
});
