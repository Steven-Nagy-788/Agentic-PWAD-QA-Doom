import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReasoningLog } from "../ReasoningLog";
import type { LiveDecision } from "@/hooks/useRunStream";

const makeDecision = (overrides: Partial<LiveDecision> = {}): LiveDecision => ({
  sequenceNumber: 1,
  ...overrides,
});

describe("ReasoningLog", () => {
  it("renders the 'Reasoning' heading", () => {
    render(<ReasoningLog decisions={[]} />);
    expect(screen.getByText("Reasoning")).toBeInTheDocument();
  });

  it("shows the count of decisions", () => {
    const decisions = [makeDecision({ sequenceNumber: 1 }), makeDecision({ sequenceNumber: 2 })];
    render(<ReasoningLog decisions={decisions} />);
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("in live mode shows only last 30 decisions when more than 30", () => {
    const decisions = Array.from({ length: 45 }, (_, i) =>
      makeDecision({ sequenceNumber: i + 1 })
    );
    render(<ReasoningLog decisions={decisions} live />);
    expect(screen.getByText("30/45")).toBeInTheDocument();
    expect(screen.getByText("#16")).toBeInTheDocument();
    expect(screen.queryByText("#1")).not.toBeInTheDocument();
  });

  it("renders a DecisionCard for each decision", () => {
    const decisions = [
      makeDecision({ sequenceNumber: 1, reasoning: "First thought" }),
      makeDecision({ sequenceNumber: 2, reasoning: "Second thought" }),
    ];
    render(<ReasoningLog decisions={decisions} />);
    expect(screen.getByText("First thought")).toBeInTheDocument();
    expect(screen.getByText("Second thought")).toBeInTheDocument();
  });

  it("SourceBadge shows 'deterministic_fallback' with amber style", () => {
    const decisions = [
      makeDecision({ sequenceNumber: 1, decisionSource: "deterministic_fallback" }),
    ];
    render(<ReasoningLog decisions={decisions} />);
    const badge = screen.getByText("deterministic_fallback");
    expect(badge).toHaveClass("bg-amber-100");
    expect(badge).toHaveClass("text-amber-800");
  });

  it("SourceBadge shows 'gemini' with neutral style", () => {
    const decisions = [
      makeDecision({ sequenceNumber: 1, decisionSource: "gemini" }),
    ];
    render(<ReasoningLog decisions={decisions} />);
    const badge = screen.getByText("gemini");
    expect(badge).toHaveClass("bg-white");
    expect(badge).toHaveClass("text-neutral-600");
  });
});
