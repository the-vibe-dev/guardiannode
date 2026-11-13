import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, type AuditEntry, type AuditPage } from "../api";
import Audit from "./Audit";

vi.mock("../api", () => ({ api: { auditPage: vi.fn() } }));
const clients: QueryClient[] = [];
const entry = (id: number, target = `target-${id}`): AuditEntry => ({ id, actor: "admin", action: "alert.view", target, source_ip: "127.0.0.1", details: {}, created_at: "2026-11-13T12:00:00Z" });
function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  clients.push(client);
  render(<QueryClientProvider client={client}><Audit /></QueryClientProvider>);
}
const apply = () => fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
beforeEach(() => vi.mocked(api.auditPage).mockResolvedValue({ items: [], next_cursor: null, total: 0 }));
afterEach(() => { cleanup(); clients.splice(0).forEach((client) => client.clear()); vi.resetAllMocks(); });

describe("complete audit history", () => {
  it("pages past 200 retained entries using every server cursor", async () => {
    vi.mocked(api.auditPage).mockImplementation(async (params) => {
      const offset = params?.cursor ? Number(params.cursor) : 0;
      const count = Math.min(50, 205 - offset);
      return { items: Array.from({ length: count }, (_, index) => entry(offset + index + 1)), total: 205, next_cursor: offset + count < 205 ? String(offset + count) : null };
    });
    show();
    expect(await screen.findByText("50 of 205 retained audit entries loaded · more available")).toBeTruthy();
    for (const count of [100, 150, 200, 205]) {
      fireEvent.click(screen.getByRole("button", { name: "Load older audit entries" }));
      await screen.findByText(`${count} of 205 retained audit entries loaded · ${count < 205 ? "more available" : "end of results"}`);
    }
    expect(screen.getByText("target-1")).toBeTruthy();
    expect(screen.getByText("target-205")).toBeTruthy();
    expect(api.auditPage).toHaveBeenLastCalledWith({ limit: "50", cursor: "200" });
    expect(screen.queryByRole("button", { name: "Load older audit entries" })).toBeNull();
  });

  it("applies exact actor/action and metadata search to the server and resets pagination", async () => {
    vi.mocked(api.auditPage).mockImplementation(async (params) => ({ items: [entry(1)], next_cursor: params?.cursor ? null : "older-page", total: 100 }));
    show();
    await screen.findByText("target-1");
    fireEvent.click(screen.getByRole("button", { name: "Load older audit entries" }));
    await waitFor(() => expect(api.auditPage).toHaveBeenLastCalledWith({ limit: "50", cursor: "older-page" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Load older audit entries" })).toBeNull());
    const loadedCalls = vi.mocked(api.auditPage).mock.calls.length;
    fireEvent.change(screen.getByLabelText("Actor (exact)"), { target: { value: " system " } });
    fireEvent.change(screen.getByLabelText("Action (exact)"), { target: { value: " retention.cleanup " } });
    fireEvent.change(screen.getByRole("searchbox", { name: "Search audit metadata" }), { target: { value: " 127.0.0.1 " } });
    expect(api.auditPage).toHaveBeenCalledTimes(loadedCalls);
    apply();
    await waitFor(() => expect(api.auditPage).toHaveBeenLastCalledWith({ limit: "50", actor: "system", action: "retention.cleanup", q: "127.0.0.1" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByLabelText("Actor (exact)")).toHaveProperty("value", "");
  });

  it("uses aware UTC boundaries for the entire through date and blocks a reversed range", async () => {
    show();
    await screen.findByText("No retained audit entries match these filters.");
    fireEvent.change(screen.getByLabelText("From date"), { target: { value: "2026-11-12" } });
    fireEvent.change(screen.getByLabelText("Through date"), { target: { value: "2026-11-12" } });
    apply();
    await waitFor(() => expect(api.auditPage).toHaveBeenLastCalledWith({ limit: "50", since: new Date("2026-11-12T00:00:00").toISOString(), until: new Date("2026-11-13T00:00:00").toISOString() }));
    const calls = vi.mocked(api.auditPage).mock.calls.length;
    fireEvent.change(screen.getByLabelText("Through date"), { target: { value: "2026-11-11" } });
    apply();
    expect(screen.getByRole("alert").textContent).toContain("on or after");
    expect(api.auditPage).toHaveBeenCalledTimes(calls);
  });

  it("never shows a late response from a superseded filter", async () => {
    let resolveOld: (page: AuditPage) => void = () => {};
    vi.mocked(api.auditPage).mockImplementation((params) => params?.actor === "old-actor"
      ? new Promise((resolve) => { resolveOld = resolve; })
      : Promise.resolve({ items: params?.actor ? [entry(2, "Current actor entry")] : [], next_cursor: null, total: params?.actor ? 1 : 0 }));
    show();
    await screen.findByText("No retained audit entries match these filters.");
    fireEvent.change(screen.getByLabelText("Actor (exact)"), { target: { value: "old-actor" } });
    apply();
    expect(screen.getByText("Loading audit history…")).toBeTruthy();
    expect(screen.queryByText("No retained audit entries match these filters.")).toBeNull();
    fireEvent.change(screen.getByLabelText("Actor (exact)"), { target: { value: "new-actor" } });
    apply();
    await screen.findByText("Current actor entry");
    await act(async () => resolveOld({ items: [entry(1, "Superseded entry")], next_cursor: null, total: 1 }));
    expect(screen.queryByText("Superseded entry")).toBeNull();
    expect(screen.getByText("Current actor entry")).toBeTruthy();
  });

  it("shows initial failure as an error, then retries without a false empty state", async () => {
    vi.mocked(api.auditPage).mockRejectedValueOnce(new Error("History unavailable"));
    show();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("History unavailable"));
    expect(screen.queryByText("No retained audit entries match these filters.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry audit history" }));
    expect(await screen.findByText("No retained audit entries match these filters.")).toBeTruthy();
  });

  it("preserves loaded entries when an older page fails and retries that same cursor", async () => {
    vi.mocked(api.auditPage)
      .mockResolvedValueOnce({ items: [entry(1, "Already loaded")], next_cursor: "page-2", total: 2 })
      .mockRejectedValueOnce(new Error("Older page unavailable"))
      .mockResolvedValueOnce({ items: [entry(2, "Older retained entry")], next_cursor: null, total: 2 });
    show();
    await screen.findByText("Already loaded");
    fireEvent.click(screen.getByRole("button", { name: "Load older audit entries" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("older audit entries"));
    expect(screen.getByText("Already loaded")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry audit history" }));
    expect(await screen.findByText("Older retained entry")).toBeTruthy();
    expect(api.auditPage).toHaveBeenLastCalledWith({ limit: "50", cursor: "page-2" });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("deduplicates repeated entries at page boundaries", async () => {
    vi.mocked(api.auditPage)
      .mockResolvedValueOnce({ items: [entry(1)], next_cursor: "page-2", total: 2 })
      .mockResolvedValueOnce({ items: [entry(1), entry(2)], next_cursor: null, total: 2 });
    show();
    await screen.findByText("target-1");
    fireEvent.click(screen.getByRole("button", { name: "Load older audit entries" }));
    await screen.findByText("target-2");
    expect(screen.getAllByText("target-1")).toHaveLength(1);
    expect(screen.getByText("2 of 2 retained audit entries loaded · end of results")).toBeTruthy();
  });
});
