import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, type Alert } from "../api";
import RiskFeed from "./RiskFeed";

vi.mock("../api", () => ({ api: { alerts: vi.fn(), devices: vi.fn(), profiles: vi.fn() } }));
const clients: QueryClient[] = [];
const makeAlert = (id: string, summary: string): Alert => ({ alert_id: id, risk_id: `risk-${id}`, device_id: "device-1", profile_id: "child-1", severity: "high", status: "open", created_at: "2026-11-12T12:00:00Z", reviewed_by: null, reviewed_at: null, action_taken: null, notes: null, summary, app_name: "ExampleChat", repeat_count: 1, categories: ["scam"] });
function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  clients.push(client);
  render(<QueryClientProvider client={client}><MemoryRouter><RiskFeed /></MemoryRouter></QueryClientProvider>);
}
beforeEach(() => {
  vi.mocked(api.devices).mockResolvedValue([{ device_id: "device-1", hostname: "Study laptop" } as never]);
  vi.mocked(api.profiles).mockResolvedValue([{ profile_id: "child-1", display_name: "Alex" } as never]);
  vi.mocked(api.alerts).mockResolvedValue({ items: [], next_cursor: null, open_count: 0 });
});
afterEach(() => { cleanup(); clients.splice(0).forEach((client) => client.clear()); vi.resetAllMocks(); });

describe("complete risk history", () => {
  it("follows the server cursor and shows the global open count", async () => {
    vi.mocked(api.alerts).mockImplementation(async (params) => params?.cursor
      ? { items: [makeAlert("old", "Older retained alert")], next_cursor: null, open_count: 73 }
      : { items: [makeAlert("new", "Recent retained alert")], next_cursor: "cursor-1", open_count: 73 });
    show();
    expect(await screen.findByText("73 open across family")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Load older alerts" }));
    expect(await screen.findByText("Older retained alert")).toBeTruthy();
    expect(screen.getByText("Recent retained alert")).toBeTruthy();
    expect(api.alerts).toHaveBeenCalledWith({ limit: "50", cursor: "cursor-1" });
    expect(screen.queryByRole("button", { name: "Load older alerts" })).toBeNull();
  });

  it("sends search to the server instead of searching only the first page", async () => {
    vi.mocked(api.alerts).mockImplementation(async (params) => ({ items: params?.q === "older evidence" ? [makeAlert("found", "Matched archived evidence")] : [], next_cursor: null, open_count: 1 }));
    show();
    fireEvent.change(screen.getByRole("searchbox", { name: "Search alerts" }), { target: { value: "older evidence" } });
    expect(await screen.findByText("Matched archived evidence")).toBeTruthy();
    expect(api.alerts).toHaveBeenCalledWith({ limit: "50", q: "older evidence" });
  });

  it("resets the cursor when child, status or severity filters change", async () => {
    vi.mocked(api.alerts).mockResolvedValue({ items: [makeAlert("one", "An alert")], next_cursor: "old-cursor", open_count: 1 });
    show();
    await screen.findByText("An alert");
    fireEvent.change(screen.getByLabelText("Child"), { target: { value: "child-1" } });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "reviewed" } });
    fireEvent.click(screen.getByRole("button", { name: "critical" }));
    await waitFor(() => expect(api.alerts).toHaveBeenLastCalledWith({ limit: "50", profile_id: "child-1", status: "reviewed", severity: "critical" }));
  });

  it("includes the entire through date and rejects reversed dates without an API call", async () => {
    show();
    await screen.findByText("No alerts yet. Signals from monitored devices will appear here.");
    fireEvent.change(screen.getByLabelText("From date"), { target: { value: "2026-11-12" } });
    fireEvent.change(screen.getByLabelText("Through date"), { target: { value: "2026-11-12" } });
    await waitFor(() => expect(api.alerts).toHaveBeenLastCalledWith({ limit: "50", since: new Date("2026-11-12T00:00:00").toISOString(), until: new Date("2026-11-13T00:00:00").toISOString() }));
    const count = vi.mocked(api.alerts).mock.calls.length;
    fireEvent.change(screen.getByLabelText("Through date"), { target: { value: "2026-11-11" } });
    expect(screen.getByRole("alert").textContent).toContain("on or after");
    expect(api.alerts).toHaveBeenCalledTimes(count);
  });

  it("shows failed requests as errors and supports retry", async () => {
    vi.mocked(api.alerts).mockRejectedValueOnce(new Error("Backend unavailable"));
    show();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Backend unavailable"));
    expect(screen.queryByText("No alerts yet. Signals from monitored devices will appear here.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No alerts yet. Signals from monitored devices will appear here.")).toBeTruthy();
  });
});
