import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatBar } from "../StatBar";

describe("StatBar", () => {
  it("renders all stat labels", () => {
    render(<StatBar state={{ health: 75, armor: 50, kills: 10, secrets: 3, tick: 250, ammo: { bullets: 20, shells: 10, rockets: 5, cells: 30 } }} />);

    expect(screen.getByText("HP")).toBeInTheDocument();
    expect(screen.getByText("Armor")).toBeInTheDocument();
    expect(screen.getByText("Ammo")).toBeInTheDocument();
    expect(screen.getByText("Kills")).toBeInTheDocument();
    expect(screen.getByText("Secrets")).toBeInTheDocument();
    expect(screen.getByText("Tick")).toBeInTheDocument();
  });

  it("displays correct stat values", () => {
    render(<StatBar state={{ health: 75, armor: 50, kills: 10, secrets: 3, tick: 250, ammo: { bullets: 20, shells: 10, rockets: 5, cells: 30 } }} />);

    expect(screen.getByLabelText("HP: 75")).toBeInTheDocument();
    expect(screen.getByLabelText("Armor: 50")).toBeInTheDocument();
    expect(screen.getByLabelText("Kills: 10")).toBeInTheDocument();
    expect(screen.getByLabelText("Secrets: 3")).toBeInTheDocument();
    expect(screen.getByLabelText("Tick: 250")).toBeInTheDocument();
  });

  it("computes total ammo correctly", () => {
    render(<StatBar state={{ tick: 0, health: 100, armor: 0, kills: 0, secrets: 0, ammo: { bullets: 20, shells: 10, rockets: 5, cells: 30 } }} />);

    expect(screen.getByLabelText("Ammo: 65")).toBeInTheDocument();
  });

  it("defaults to 0 for missing values", () => {
    render(<StatBar state={null} />);

    expect(screen.getByLabelText("HP: 0")).toBeInTheDocument();
    expect(screen.getByLabelText("Armor: 0")).toBeInTheDocument();
    expect(screen.getByLabelText("Kills: 0")).toBeInTheDocument();
    expect(screen.getByLabelText("Secrets: 0")).toBeInTheDocument();
    expect(screen.getByLabelText("Tick: 0")).toBeInTheDocument();
  });

  it("handles partial ammo object", () => {
    render(<StatBar state={{ tick: 0, health: 100, armor: 0, kills: 0, secrets: 0, ammo: { bullets: 20 } }} />);

    expect(screen.getByLabelText("Ammo: 20")).toBeInTheDocument();
  });
});
