import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, type DeviceAction } from "../api";
import ActionHistory from "./ActionHistory";
import { formatDateTime } from "../utils/datetime";

vi.mock("../api", () => ({ api: { alertActions: vi.fn(), undoAction: vi.fn() } }));
const clients: QueryClient[] = [];
const base: DeviceAction = { action_id: "pause-1", alert_id: "alert-1", device_id: "device-1", action: "pause_app", status: "succeeded", preview: "Pause C:\\Apps\\Chat.exe for 15 minutes", created_at: "2026-11-13T12:00:00Z", completed_at: "2026-11-13T12:00:05Z", expires_at: "2099-11-14T12:00:00Z", undo_of: null, execution: null };
function show(alertId = "alert-1") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  clients.push(client);
  const view = render(<QueryClientProvider client={client}><ActionHistory alertId={alertId} /></QueryClientProvider>);
  return { changeAlert: (id: string) => view.rerender(<QueryClientProvider client={client}><ActionHistory alertId={id} /></QueryClientProvider>) };
}
const undoButton = () => screen.getByRole("button", { name: `Queue undo: ${base.preview}` });
beforeEach(() => vi.mocked(api.alertActions).mockResolvedValue([base]));
afterEach(() => { cleanup(); clients.splice(0).forEach((client) => client.clear()); vi.resetAllMocks(); });

describe("last-reported device action history", () => {
  it("distinguishes queued and claimed commands and refreshes their latest report", async () => {
    vi.mocked(api.alertActions)
      .mockResolvedValueOnce([{ ...base, status: "queued", completed_at: null }, { ...base, action_id: "notice-1", action: "show_child_prompt", status: "claimed", preview: "Child notice", completed_at: null }])
      .mockResolvedValueOnce([base]);
    show();
    expect(await screen.findByText("Queued")).toBeTruthy();
    expect(screen.getByText("Claimed by device")).toBeTruthy();
    expect(screen.getByText("Waiting for the device to receive this command.")).toBeTruthy();
    expect(screen.queryByText("No actions have been recorded for this alert.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Refresh action history" }));
    expect(await screen.findByText("Succeeded")).toBeTruthy();
    expect(screen.getByText(/Status reflects the latest received command result/)).toBeTruthy();
  });

  it("warns about a failed pause with an active lease and keeps undo available", async () => {
    const pauseDeadline = "2026-11-13T12:15:00Z";
    vi.mocked(api.alertActions).mockResolvedValue([{ ...base, status: "failed", execution: { has_error: true, lease_status: "active", lease_expires_at: pauseDeadline, partial_failure: true, suspended_processes: 1, failed_processes: 1 } }]);
    show();
    const warning = await screen.findByRole("alert");
    expect(warning.textContent).toContain(`some processes may remain paused until ${formatDateTime(pauseDeadline)} or until undo is applied`);
    expect(screen.getByText(`Command delivery deadline: ${formatDateTime(base.expires_at)}`)).toBeTruthy();
    expect(screen.getByText(new RegExp(`Last report: ${formatDateTime(base.completed_at).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`))).toBeTruthy();
    expect(undoButton()).toHaveProperty("disabled", false);
    expect(screen.getByText("Failed")).toBeTruthy();
  });

  it("does not treat a pending resume or overlapping pause as fully restored", async () => {
    const execution = { has_error: true, pending_resume_processes: 1, pending_recovery_processes: 2, active_pause_leases: 1, resumed_processes: 0, lease_status: "undone" };
    const reportedUndo = { ...base, action_id: "undo-1", action: "undo_action", undo_of: base.action_id, status: "failed", preview: `Undo: ${base.preview}`, execution };
    vi.mocked(api.alertActions).mockResolvedValue([reportedUndo, base]);
    show();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("processes waiting to resume: 1; processes waiting for recovery: 2"));
    expect(screen.getByText(/1 other pause leases remained active/)).toBeTruthy();
    expect(undoButton()).toHaveProperty("disabled", false);
    expect(screen.queryByText(/An active or successful undo is already recorded/)).toBeNull();
    expect(screen.queryByText(/fully restored/i)).toBeNull();

    vi.mocked(api.alertActions).mockResolvedValue([{ ...reportedUndo, execution: { ...execution, pending_resume_processes: null } }, base]);
    fireEvent.click(screen.getByRole("button", { name: "Refresh action history" }));
    expect(await screen.findByText(/processes waiting to resume: not reported; processes waiting for recovery: 2/)).toBeTruthy();

    vi.mocked(api.alertActions).mockResolvedValue([{ ...reportedUndo, execution: { ...execution, pending_recovery_processes: undefined } }, base]);
    fireEvent.click(screen.getByRole("button", { name: "Refresh action history" }));
    expect(await screen.findByText(/processes waiting to resume: 1; processes waiting for recovery: not reported/)).toBeTruthy();
  });

  it("queues undo only after the parent clicks and suppresses duplicate undo immediately", async () => {
    let complete!: (action: DeviceAction) => void;
    const queued: DeviceAction = { ...base, action_id: "undo-1", action: "undo_action", status: "queued", completed_at: null, preview: `Undo: ${base.preview}`, undo_of: base.action_id };
    vi.mocked(api.undoAction).mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
    show();
    await screen.findByText(base.preview);
    expect(api.undoAction).not.toHaveBeenCalled();
    fireEvent.click(undoButton());
    expect(await screen.findByText("Requesting undo…")).toBeTruthy();
    expect(screen.queryByText(/Undo is queued\./)).toBeNull();
    await waitFor(() => expect(api.undoAction).toHaveBeenCalledWith(base.action_id, expect.anything()));
    vi.mocked(api.alertActions).mockResolvedValue([queued, base]);
    await act(async () => complete(queued));
    expect(await screen.findByText("Undo is queued. It is not applied until the endpoint reports its result. Check the undo entry below.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Queue undo:/ })).toBeNull();
    expect(screen.getByText(queued.preview)).toBeTruthy();
    expect(api.undoAction).toHaveBeenCalledTimes(1);
  });

  it("updates the undo banner when an endpoint result arrives without hiding other active pauses", async () => {
    const queued: DeviceAction = { ...base, action_id: "undo-1", action: "undo_action", status: "queued", completed_at: null, preview: `Undo: ${base.preview}`, undo_of: base.action_id };
    vi.mocked(api.undoAction).mockResolvedValue(queued);
    show();
    await screen.findByText(base.preview);
    vi.mocked(api.alertActions).mockResolvedValue([queued, base]);
    fireEvent.click(undoButton());
    await screen.findByText(/Undo is queued\./);
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh action history" })).toHaveProperty("disabled", false));
    vi.mocked(api.alertActions).mockResolvedValue([{ ...queued, status: "succeeded", completed_at: "2026-11-13T12:01:00Z", execution: { has_error: false, active_pause_leases: 1 } }, base]);
    fireEvent.click(screen.getByRole("button", { name: "Refresh action history" }));
    expect(await screen.findByText(/Latest undo report: Succeeded/)).toBeTruthy();
    expect(screen.queryByText(/Undo is queued\./)).toBeNull();
    expect(screen.getByText(/other pause leases remained active/)).toBeTruthy();
  });

  it.each(["failed", "rejected", "expired", "queued"])("allows recovery retry after an unsuccessful or overdue %s undo", async (status) => {
    const unsuccessful: DeviceAction = { ...base, action_id: "undo-old", action: "undo_action", undo_of: base.action_id, status, preview: `Undo: ${base.preview}`, expires_at: "2000-01-01T00:00:00Z", execution: { has_error: true, pending_domain_blocks: 1 } };
    vi.mocked(api.alertActions).mockResolvedValue([unsuccessful, base]);
    const queued: DeviceAction = { ...unsuccessful, action_id: "undo-new", status: "queued", expires_at: "2099-01-01T00:00:00Z" };
    vi.mocked(api.undoAction).mockResolvedValue(queued);
    show();
    await screen.findByText(base.preview);
    expect(screen.getByRole("alert").textContent).toContain("1 legacy domain blocks still require removal");
    expect(undoButton()).toHaveProperty("disabled", false);
    vi.mocked(api.alertActions).mockResolvedValue([queued, unsuccessful, base]);
    fireEvent.click(undoButton());
    await screen.findByText(/Undo is queued/);
    expect(api.undoAction).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /^Queue undo:/ })).toBeNull();
  });

  it("reports an undo request failure and keeps a safe retry available", async () => {
    vi.mocked(api.undoAction).mockRejectedValue(new Error("Device command service unavailable"));
    show();
    await screen.findByText(base.preview);
    fireEvent.click(undoButton());
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Could not queue undo: Device command service unavailable"));
    expect(screen.queryByText(/Undo is queued\./)).toBeNull();
    await waitFor(() => expect(undoButton()).toHaveProperty("disabled", false));
    expect(screen.getByText(base.preview)).toBeTruthy();
  });

  it("isolates action-history failures from an empty history and retries", async () => {
    vi.mocked(api.alertActions).mockRejectedValueOnce(new Error("History offline")).mockResolvedValueOnce([]);
    show();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("History offline"));
    expect(screen.queryByText("No actions have been recorded for this alert.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry action history" }));
    expect(await screen.findByText("No actions have been recorded for this alert.")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("ignores a late action history response from a previous alert", async () => {
    let oldResponse!: (actions: DeviceAction[]) => void;
    vi.mocked(api.alertActions).mockImplementation((id) => id === "previous" ? new Promise((resolve) => { oldResponse = resolve; }) : Promise.resolve([{ ...base, alert_id: id, preview: "Current incident action" }]));
    const view = show("previous");
    expect(screen.getByText("Loading action history…")).toBeTruthy();
    view.changeAlert("current");
    await screen.findByText("Current incident action");
    await act(async () => oldResponse([{ ...base, preview: "Previous incident action" }]));
    expect(screen.queryByText("Previous incident action")).toBeNull();
    expect(screen.getByText("Current incident action")).toBeTruthy();
  });
});
