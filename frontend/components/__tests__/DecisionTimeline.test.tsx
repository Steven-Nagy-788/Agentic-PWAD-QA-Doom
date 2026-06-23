import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DecisionTimeline } from "../DecisionTimeline";
import type { Decision } from "@/lib/api";

const makeDecision = (overrides: Partial<Decision> = {}): Decision => ({
  id: "d1",
  run_id: "r1",
  sequence_number: 1,
  status: "completed",
  decision_source: "gemini",
  ...overrides,
});

describe("DecisionTimeline", () => {
  it("renders empty list without errors", () => {
    const { container } = render(<DecisionTimeline decisions={[]} />);
    expect(container.querySelector("[role='list']")).toBeInTheDocument();
    expect(container.querySelectorAll("[role='listitem']").length).toBe(0);
  });

  it("renders decision with sequence_number and mcp_tool", () => {
    const decision = makeDecision({ sequence_number: 5, mcp_tool: "take_action" });
    render(<DecisionTimeline decisions={[decision]} />);
    expect(screen.getByText(/#5 take_action/)).toBeInTheDocument();
  });

  it("shows tick_before and tick_after", () => {
    const decision = makeDecision({ tick_before: 100, tick_after: 110 });
    render(<DecisionTimeline decisions={[decision]} />);
    expect(screen.getByText(/100.*to.*110/)).toBeInTheDocument();
  });

  it("shows reasoning_summary in expanded details", () => {
    const decision = makeDecision({ reasoning_summary: "Move forward to explore area" });
    render(<DecisionTimeline decisions={[decision]} />);
    expect(screen.getByText("Move forward to explore area")).toBeInTheDocument();
  });

  it("shows validation_rejection in red when present", () => {
    const decision = makeDecision({ validation_rejection: "out of bounds" });
    render(<DecisionTimeline decisions={[decision]} />);
    const rejection = screen.getByText(/rejected: out of bounds/);
    expect(rejection).toBeInTheDocument();
    expect(rejection.className).toContain("text-red-600");
  });
});
