import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { api, type NotificationStatus } from "../api";
import NotificationDelivery from "./NotificationDelivery";

vi.mock("../api", () => ({ api: { notificationStatus: vi.fn() } }));
const clients: QueryClient[] = [];
const status: NotificationStatus = {
  enabled: true, consent_allowed: true, worker_enabled: true,
  channels: { email: { configured: true, last_success_at: "2026-11-12T12:00:00Z" }, webhook: { configured: false, last_success_at: null } },
  counts: { queued: 1, retry: 2, processing: 0, sent: 8, dead: 1, skipped: 0 },
  recent_jobs: [{ id: 1, alert_id: "alert-1", severity: "high", status: "retry", attempts: 2, next_attempt_at: "2026-11-12T13:00:00Z", created_at: "2026-11-12T12:00:00Z", updated_at: "2026-11-12T12:10:00Z", delivered_channels: ["email"] }],
  recent_attempts: [], last_digest: { local_date: "2026-11-11", timezone: "America/New_York", status: "sent", total_alerts: 4, completed_at: "2026-11-12T13:00:00Z" },
};
function show() { const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }); clients.push(client); render(<QueryClientProvider client={client}><MemoryRouter><NotificationDelivery /></MemoryRouter></QueryClientProvider>); }
afterEach(() => { cleanup(); clients.splice(0).forEach((client) => client.clear()); vi.resetAllMocks(); });
describe("notification delivery diagnostics", () => {
  it("distinguishes retry backlog and exhausted jobs from successful transport acceptance", async () => {
    vi.mocked(api.notificationStatus).mockResolvedValue(status);
    show();
    expect(await screen.findByText("Some notifications exhausted their retries. Check the channel settings and send a test. Historical failures remain in this list.")).toBeTruthy();
    expect(screen.getAllByText("Waiting to retry").length).toBeGreaterThan(0);
    expect(screen.getByText(/it does not confirm that someone read it/)).toBeTruthy();
    fireEvent.click(screen.getByText("Recent delivery jobs (1)"));
    expect(screen.getByRole("link", { name: "high alert" }).getAttribute("href")).toBe("/alerts/alert-1");
    expect(screen.getByText("2026-11-11")).toBeTruthy();
  });
  it("explains a disabled worker without pretending queued jobs will send", async () => {
    vi.mocked(api.notificationStatus).mockResolvedValue({ ...status, worker_enabled: false });
    show();
    expect(await screen.findByText(/The notification worker is disabled/)).toBeTruthy();
  });
  it("recovers independently from a failed status request", async () => {
    vi.mocked(api.notificationStatus).mockRejectedValueOnce(new Error("Unavailable")).mockResolvedValue(status);
    show();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Delivery status is unavailable"));
    fireEvent.click(screen.getByRole("button", { name: "Retry delivery status" }));
    expect(await screen.findByText("Needs attention")).toBeTruthy();
  });
  it("explains a job skipped after policy changes and displays the saved severity threshold", async () => {
    vi.mocked(api.notificationStatus).mockResolvedValue({ ...status, routing: { immediate_min_severity: "critical", protected_safety_floor: "high", rechecks_current_policy: true, historical_backfill: false }, recent_jobs: [{ ...status.recent_jobs[0], status: "skipped", skip_reason: "current_policy" }] });
    show();
    await screen.findByText("critical");
    fireEvent.click(screen.getByText("Recent delivery jobs (1)"));
    expect(screen.getByText("No longer eligible under the current policy or threshold.")).toBeTruthy();
    expect(screen.getByText(/Protected safety categories retain their High\/Critical exception/)).toBeTruthy();
  });
});
