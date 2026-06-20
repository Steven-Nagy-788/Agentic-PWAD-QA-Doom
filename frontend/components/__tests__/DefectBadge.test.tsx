import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DefectBadge } from "../DefectBadge";

describe("DefectBadge", () => {
  it("renders zero defects with emerald tone", () => {
    render(<DefectBadge count={0} />);
    const badge = screen.getByLabelText("0 defects");
    expect(badge).toHaveClass("bg-emerald-50");
    expect(badge).toHaveTextContent("0");
  });

  it("renders 1 defect with amber tone", () => {
    render(<DefectBadge count={1} />);
    const badge = screen.getByLabelText("1 defect");
    expect(badge).toHaveClass("bg-amber-50");
    expect(badge).toHaveTextContent("1");
  });

  it("renders 2 defects with amber tone", () => {
    render(<DefectBadge count={2} />);
    const badge = screen.getByLabelText("2 defects");
    expect(badge).toHaveClass("bg-amber-50");
  });

  it("renders 5 defects with red tone", () => {
    render(<DefectBadge count={5} />);
    const badge = screen.getByLabelText("5 defects");
    expect(badge).toHaveClass("bg-red-50");
    expect(badge).toHaveTextContent("5");
  });

  it("applies pulse animation when pulse=true", () => {
    render(<DefectBadge count={3} pulse />);
    const badge = screen.getByLabelText("3 defects");
    expect(badge).toHaveClass("animate-pulse");
  });

  it("does not apply pulse when pulse=false", () => {
    render(<DefectBadge count={3} pulse={false} />);
    const badge = screen.getByLabelText("3 defects");
    expect(badge).not.toHaveClass("animate-pulse");
  });
});
