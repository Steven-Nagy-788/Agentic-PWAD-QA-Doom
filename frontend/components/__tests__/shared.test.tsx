import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { formatBytes, formatTime, OutcomeBadge, errorMessage } from "@/lib/components/shared";

describe("formatBytes", () => {
  it("returns bytes for values < 1024", () => {
    expect(formatBytes(500)).toBe("500 B");
  });

  it("formats 1024 as 1.0 KB", () => {
    expect(formatBytes(1024)).toBe("1.0 KB");
  });

  it("formats 1536 as 1.5 KB", () => {
    expect(formatBytes(1536)).toBe("1.5 KB");
  });

  it("formats 1048576 as 1.0 MB", () => {
    expect(formatBytes(1048576)).toBe("1.0 MB");
  });

  it("formats 2621440 as 2.5 MB", () => {
    expect(formatBytes(2621440)).toBe("2.5 MB");
  });
});

describe("formatTime", () => {
  it("returns 'just now' for a timestamp less than 5 seconds ago", () => {
    const ts = Date.now() - 2 * 1000;
    expect(formatTime(ts)).toBe("just now");
  });

  it("returns '30s ago' for a timestamp 30 seconds ago", () => {
    const ts = Date.now() - 30 * 1000;
    expect(formatTime(ts)).toBe("30s ago");
  });

  it("returns '2m ago' for a timestamp 120 seconds ago", () => {
    const ts = Date.now() - 120 * 1000;
    expect(formatTime(ts)).toBe("2m ago");
  });
});

describe("OutcomeBadge", () => {
  it("renders emerald tone for 'map_completed'", () => {
    render(<OutcomeBadge outcome="map_completed" />);
    const badge = screen.getByText("map_completed");
    expect(badge.className).toContain("emerald");
  });

  it("renders red tone for 'pwad_crash'", () => {
    render(<OutcomeBadge outcome="pwad_crash" />);
    const badge = screen.getByText("pwad_crash");
    expect(badge.className).toContain("red");
  });

  it("renders amber tone for 'timeout'", () => {
    render(<OutcomeBadge outcome="timeout" />);
    const badge = screen.getByText("timeout");
    expect(badge.className).toContain("amber");
  });

  it("renders 'unknown' with amber tone when outcome is null", () => {
    render(<OutcomeBadge outcome={null} />);
    const badge = screen.getByText("unknown");
    expect(badge.className).toContain("amber");
  });
});

describe("errorMessage", () => {
  it("returns the message from an Error instance", () => {
    const err = new Error("something broke");
    expect(errorMessage(err)).toBe("something broke");
  });

  it("returns undefined for a non-Error value", () => {
    expect(errorMessage("not an error")).toBeUndefined();
  });
});
