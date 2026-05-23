import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MapCanvas } from "../MapCanvas";
import { PositionSample, TraceEntry, WadMap } from "@/lib/api";

describe("MapCanvas", () => {
  const mockMap: WadMap = {
    wad_file_id: "wad1",
    map_name: "MAP01",
    iwad_required: "doom2",
    analyzed: true,
    map_overview_png_url: "/maps/wad1/MAP01/overview.png",
  };

  it("renders map image when available", () => {
    render(<MapCanvas map={mockMap} />);
    const img = screen.getByAltText("MAP01 overview");
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("src", expect.stringContaining("overview.png"));
  });

  it("shows grid background when no map image", () => {
    render(<MapCanvas map={null} />);
    const img = screen.queryByRole("img");
    expect(img).not.toBeInTheDocument();
  });

  it("renders trail dots", () => {
    const trail: PositionSample[] = [
      { id: 1, run_id: "r1", tick_number: 0, x: 100, y: 100, health: 100 },
      { id: 2, run_id: "r1", tick_number: 1, x: 200, y: 200, health: 90 },
      { id: 3, run_id: "r1", tick_number: 2, x: 300, y: 300, health: 80 },
    ];

    const { container } = render(<MapCanvas map={mockMap} trail={trail} />);
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();

    const circles = svg!.querySelectorAll("circle");
    const trailCircles = Array.from(circles).filter((c) => c.getAttribute("fill")?.includes("rgba"));
    expect(trailCircles).toHaveLength(3);
  });

  it("renders event markers with correct colors", () => {
    const events: TraceEntry[] = [
      { id: 1, run_id: "r1", tick_number: 5, player_x: 150, player_y: 150, player_angle: 0, health: 100, armor: 0, ammo_bullets: 10, ammo_shells: 0, ammo_rockets: 0, ammo_cells: 0, kill_count: 1, item_count: 0, secret_count: 0, event_type: "kill" },
      { id: 2, run_id: "r1", tick_number: 10, player_x: 250, player_y: 250, player_angle: 0, health: 50, armor: 0, ammo_bullets: 10, ammo_shells: 0, ammo_rockets: 0, ammo_cells: 0, kill_count: 1, item_count: 0, secret_count: 0, event_type: "item_pickup" },
      { id: 3, run_id: "r1", tick_number: 15, player_x: 350, player_y: 350, player_angle: 0, health: 0, armor: 0, ammo_bullets: 10, ammo_shells: 0, ammo_rockets: 0, ammo_cells: 0, kill_count: 1, item_count: 0, secret_count: 0, event_type: "death" },
    ];

    const { container } = render(<MapCanvas map={mockMap} events={events} />);
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();

    const deathLines = svg!.querySelectorAll("line");
    expect(deathLines.length).toBeGreaterThan(0);
  });

  it("renders live position indicator when provided", () => {
    const trail: PositionSample[] = [
      { id: 1, run_id: "r1", tick_number: 0, x: 0, y: 0, health: 100 },
    ];

    const { container } = render(<MapCanvas map={mockMap} trail={trail} livePosition={{ x: 500, y: 500 }} />);
    const svg = container.querySelector("svg");
    const circles = svg!.querySelectorAll("circle");
    const liveCircle = Array.from(circles).find((c) => c.getAttribute("fill") === "#0891b2");
    expect(liveCircle).toBeInTheDocument();
  });

  it("is keyboard navigable", () => {
    const { container } = render(<MapCanvas map={mockMap} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("tabindex", "0");
    expect(svg).toHaveAttribute("role", "application");
  });
});
