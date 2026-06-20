import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AsciiGrid } from "../AsciiGrid";

describe("AsciiGrid", () => {
  it("renders no data message when grid is null", () => {
    render(<AsciiGrid grid={null} />);
    expect(screen.getByText("No grid data available")).toBeInTheDocument();
  });

  it("renders no data message when grid is undefined", () => {
    render(<AsciiGrid grid={undefined} />);
    expect(screen.getByText("No grid data available")).toBeInTheDocument();
  });

  it("renders grid characters", () => {
    const grid = "P..E\n.I..\n..#.";
    const { container } = render(<AsciiGrid grid={grid} />);
    const pre = container.querySelector("pre");
    expect(pre).toBeInTheDocument();
    expect(pre?.textContent).toContain("P");
    expect(pre?.textContent).toContain("E");
    expect(pre?.textContent).toContain("I");
    expect(pre?.textContent).toContain("#");
  });

  it("separates header lines from grid lines", () => {
    const grid = "Player at (100, 200)\nLegend: P=player\nP..E\n.I..";
    const { container } = render(<AsciiGrid grid={grid} />);
    const pre = container.querySelector("pre");
    expect(pre).toBeInTheDocument();
    expect(pre?.textContent).toContain("P..E");
    expect(pre?.textContent).toContain(".I..");
  });

  it("shows legend with all character types", () => {
    const { container } = render(<AsciiGrid grid="P" />);
    const legendDiv = container.querySelector(".mt-1.text-\\[9px\\]");
    expect(legendDiv).toBeInTheDocument();
    expect(legendDiv?.textContent).toContain("=enemy");
    expect(legendDiv?.textContent).toContain("=item");
    expect(legendDiv?.textContent).toContain("=weapon");
    expect(legendDiv?.textContent).toContain("=key");
    expect(legendDiv?.textContent).toContain("=door");
    expect(legendDiv?.textContent).toContain("=player");
    expect(legendDiv?.textContent).toContain("=unexplored");
  });

  it("applies custom className", () => {
    const { container } = render(<AsciiGrid grid="P" className="h-64" />);
    expect(container.firstChild).toHaveClass("h-64");
  });
});
