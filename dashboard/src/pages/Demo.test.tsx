import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Demo from "./Demo";
import { api } from "../api";

vi.mock("../api", () => ({
  api: {
    demoStatus: vi.fn(),
    demoScenarios: vi.fn(),
    triggerDemoScenario: vi.fn(),
    resetDemo: vi.fn(),
  },
}));

beforeEach(() => {
  vi.mocked(api.demoStatus).mockResolvedValue({
    enabled: true,
    device: { status: "demo_ready" },
    guardian_review: { ready: true, model: "gpt-5.6" },
  });
  vi.mocked(api.demoScenarios).mockResolvedValue([{
    id: "harmless-control",
    title: "Clearly harmless control scenario",
    description: "A normal family message.",
    expected_local_severity: "none",
  }]);
  vi.mocked(api.triggerDemoScenario).mockResolvedValue({
    alert_url: "/alerts/demo-alert-1",
    local_detection: { severity: "none", categories: [] },
  });
  vi.mocked(api.resetDemo).mockResolvedValue({ alerts_removed: 1 });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("synthetic judge demo", () => {
  it("guides a judge from scenario through the real incident route", async () => {
    render(<MemoryRouter><Demo /></MemoryRouter>);
    expect(await screen.findByText("gpt-5.6 ready")).toBeTruthy();
    fireEvent.click(screen.getByText("Trigger synthetic incident"));
    await waitFor(() => expect(api.triggerDemoScenario).toHaveBeenCalledWith("harmless-control"));
    const link = await screen.findByText(/Open incident and continue/);
    expect(link.getAttribute("href")).toBe("/alerts/demo-alert-1");
    expect(screen.getByText(/no rule matched/)).toBeTruthy();
  });
});
