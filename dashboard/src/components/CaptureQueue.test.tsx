import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, type CaptureQueueStatus } from "../api";
import CaptureQueue from "./CaptureQueue";

vi.mock("../api", () => ({ api: { captureQueue: vi.fn(), updateCaptureQueuePolicy: vi.fn(), runCaptureQueueCleanup: vi.fn() } }));
const clients: QueryClient[] = [];
const inventory = { files: 0, frames: 0, bytes: 0, oldest_at: null, orphan_files: 0, unsafe_files: 0, scan_truncated: false };
const initial: CaptureQueueStatus = {
  policy: { dead_letter_retention_days: 7, dead_letter_max_bytes: 268435456, cleanup_batch_files: 256 },
  worker: { enabled: true, interval_seconds: 60 },
  pending: { ...inventory, files: 4, frames: 2, bytes: 8192 },
  dead_letter: { ...inventory, files: 2, frames: 1, bytes: 4096 },
  cleanup: { last_run_at: null, deleted_files: 0, deleted_bytes: 0, expired_files: 0, quota_files: 0, failed_files: 0, budget_exhausted: false, scan_truncated: false },
  withdrawal_cleanup: { pending: false, requested_at: null, last_attempt_at: null, attempts: 0, remaining_files: 0, remaining_events: 0, remaining_blobs: 0, inventory_incomplete: false, last_deleted_files: 0, last_failed_files: 0 },
};
function show(onCleanup?: () => Promise<void>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  clients.push(client);
  render(<QueryClientProvider client={client}><CaptureQueue onCleanup={onCleanup} /></QueryClientProvider>);
}
beforeEach(() => {
  vi.mocked(api.captureQueue).mockResolvedValue(structuredClone(initial));
  vi.mocked(api.updateCaptureQueuePolicy).mockImplementation(async (policy) => ({ ...structuredClone(initial), policy: { ...initial.policy, ...policy } }));
  vi.mocked(api.runCaptureQueueCleanup).mockResolvedValue(structuredClone(initial));
});
afterEach(() => { cleanup(); clients.splice(0).forEach((client) => client.clear()); vi.resetAllMocks(); });

describe("capture queue controls and truthful deletion status", () => {
  it("renders bounded inventories as lower bounds and does not claim incomplete deletion is done", async () => {
    vi.mocked(api.captureQueue).mockResolvedValue({ ...structuredClone(initial), pending: { ...initial.pending, scan_truncated: true }, withdrawal_cleanup: { ...initial.withdrawal_cleanup, requested_at: "2026-11-13T12:00:00Z", inventory_incomplete: true } });
    show();
    expect(await screen.findByText("At least 2 captures · 4 files · 8.0 KiB")).toBeTruthy();
    expect(screen.getByText(/These counts are lower bounds/)).toBeTruthy();
    expect(screen.getByText("Deletion remains queued for retry.")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("Additional files may remain");
    expect(screen.queryByText("The recorded evidence deletion request is complete.")).toBeNull();
  });

  it("saves validated policy in bytes and keeps the draft during a status refresh", async () => {
    show();
    await screen.findByLabelText("Quarantine storage limit (MiB)");
    fireEvent.change(screen.getByLabelText("Quarantine storage limit (MiB)"), { target: { value: "128" } });
    fireEvent.change(screen.getByLabelText("Quarantine retention (days)"), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Refresh queue status" }));
    await waitFor(() => expect(api.captureQueue).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh queue status" })).toHaveProperty("disabled", false));
    expect(screen.getByLabelText("Quarantine storage limit (MiB)")).toHaveProperty("value", "128");
    fireEvent.click(screen.getByRole("button", { name: "Save queue policy" }));
    await screen.findByText("Capture queue policy saved. Cleanup uses this policy on its next run.");
    expect(api.updateCaptureQueuePolicy).toHaveBeenCalledWith({ dead_letter_retention_days: 5, dead_letter_max_bytes: 134217728, cleanup_batch_files: 256 }, expect.anything());
    expect(screen.queryByRole("button", { name: "Discard queue policy edits" })).toBeNull();
  });

  it("blocks invalid or blank policy fields before sending changes", async () => {
    show();
    await screen.findByLabelText("Quarantine retention (days)");
    for (const value of ["", "0", "91", "1.5"]) {
      fireEvent.change(screen.getByLabelText("Quarantine retention (days)"), { target: { value } });
      fireEvent.click(screen.getByRole("button", { name: "Save queue policy" }));
      expect(screen.getByRole("alert").textContent).toContain("1–90 whole days");
    }
    expect(api.updateCaptureQueuePolicy).not.toHaveBeenCalled();
  });

  it("keeps the policy draft and reports a save failure without a success message", async () => {
    vi.mocked(api.updateCaptureQueuePolicy).mockRejectedValueOnce(new Error("Settings locked"));
    show();
    await screen.findByLabelText("Quarantine retention (days)");
    fireEvent.change(screen.getByLabelText("Quarantine retention (days)"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save queue policy" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Queue policy was not saved: Settings locked"));
    expect(screen.getByLabelText("Quarantine retention (days)")).toHaveProperty("value", "12");
    expect(screen.queryByText(/Capture queue policy saved/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save queue policy" }));
    expect(await screen.findByText(/Capture queue policy saved/)).toBeTruthy();
  });

  it("retries a failed initial load without exposing empty counters as a successful inventory", async () => {
    vi.mocked(api.captureQueue).mockRejectedValueOnce(new Error("Queue unavailable"));
    show();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Queue unavailable"));
    expect(screen.queryByText("No evidence deletion request recorded.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry queue status" }));
    expect(await screen.findByText("No evidence deletion request recorded.")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("runs cleanup with the saved policy, retains edits, and shows remaining work after a partial attempt", async () => {
    const after = { ...structuredClone(initial), cleanup: { ...initial.cleanup, last_run_at: "2026-11-13T12:00:00Z", deleted_files: 2, deleted_bytes: 4096, failed_files: 1, budget_exhausted: true }, withdrawal_cleanup: { ...initial.withdrawal_cleanup, requested_at: "2026-11-13T11:00:00Z", pending: true, remaining_files: 3, remaining_events: 1, attempts: 1, last_failed_files: 1 } };
    vi.mocked(api.runCaptureQueueCleanup).mockResolvedValue(after);
    const refreshed = vi.fn().mockResolvedValue(undefined);
    show(refreshed);
    await screen.findByLabelText("Quarantine retention (days)");
    fireEvent.change(screen.getByLabelText("Quarantine retention (days)"), { target: { value: "14" } });
    fireEvent.click(screen.getByRole("button", { name: "Run queue cleanup" }));
    expect(await screen.findByText(/Queue cleanup attempt finished: 2 queued capture files removed/)).toBeTruthy();
    expect(screen.getByText("Deletion remains queued for retry.")).toBeTruthy();
    expect(screen.getByText(/Remaining known targets: 3 queued files, 1 event records/)).toBeTruthy();
    expect(screen.getByText(/This cleanup reached its file or scan limit/)).toBeTruthy();
    expect(screen.getByLabelText("Quarantine retention (days)")).toHaveProperty("value", "14");
    expect(api.updateCaptureQueuePolicy).not.toHaveBeenCalled();
    expect(refreshed).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("The recorded evidence deletion request is complete.")).toBeNull();
  });

  it("reports a completed request only when no retry or inventory uncertainty remains", async () => {
    vi.mocked(api.captureQueue).mockResolvedValue({ ...structuredClone(initial), withdrawal_cleanup: { ...initial.withdrawal_cleanup, requested_at: "2026-11-13T11:00:00Z", attempts: 2 } });
    show();
    expect(await screen.findByText("The recorded evidence deletion request is complete.")).toBeTruthy();
    expect(screen.queryByText("Deletion remains queued for retry.")).toBeNull();
    expect(screen.getByText("Backups, existing exports, and downloaded copies are not included.")).toBeTruthy();
  });

  it("shows a disabled worker and keeps stale counts clearly marked when refresh fails", async () => {
    vi.mocked(api.captureQueue).mockResolvedValueOnce({ ...structuredClone(initial), worker: { enabled: false, interval_seconds: 60 } }).mockRejectedValueOnce(new Error("Offline"));
    show();
    await screen.findByText(/Automatic queue housekeeping is disabled/);
    fireEvent.click(screen.getByRole("button", { name: "Refresh queue status" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Previously loaded counts may be out of date"));
    expect(screen.getByText("2 captures · 4 files · 8.0 KiB")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Run queue cleanup" })).toBeTruthy();
  });
});
