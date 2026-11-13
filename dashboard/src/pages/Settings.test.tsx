import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { api } from "../api";
import Settings from "./Settings";

vi.mock("../components/CaptureQueue", () => ({ default: () => <section>Capture queue settings</section> }));

vi.mock("../api", () => ({ api: {
  notificationSettings: vi.fn(), retentionSettings: vi.fn(), storage: vi.fn(), exports: vi.fn(), backupSettings: vi.fn(), guardianReviewProviders: vi.fn(), familyLocale: vi.fn(), notificationStatus: vi.fn(), testNotificationSettings: vi.fn(), wipeStorage: vi.fn(),
  updateNotificationSettings: vi.fn(), updateRetentionSettings: vi.fn(), updateBackupSettings: vi.fn(), updateFamilyLocale: vi.fn(), runCompleteBackup: vi.fn(), runRetentionCleanup: vi.fn(),
} }));
const clients: QueryClient[] = [];
function show() { const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }); clients.push(client); render(<QueryClientProvider client={client}><MemoryRouter><Settings /></MemoryRouter></QueryClientProvider>); }
beforeEach(() => {
  vi.mocked(api.notificationSettings).mockResolvedValue({ enabled: true, host: "smtp.example.test", port: 587, tls_mode: "starttls", username: "", password: "", from_address: "", to_address: "", webhook_url: "", daily_digest_enabled: true, daily_digest_time: "08:00" });
  vi.mocked(api.retentionSettings).mockResolvedValue({ critical: 90, high: 90, medium: 30, low: 1, none: 0, screenshots_flagged: 30, audit_logs: 180 });
  vi.mocked(api.storage).mockResolvedValue({ alerts: 1, events: 2, risk_results: 2, evidence_blobs: 1, evidence_bytes: 4096, export_bytes: 0 });
  vi.mocked(api.exports).mockResolvedValue([]);
  vi.mocked(api.backupSettings).mockResolvedValue({ config: { enabled: false, destination: "/backup", retention_count: 7, interval_seconds: 86400, recipient_public_key: "", incremental_evidence: false }, runs: [] });
  vi.mocked(api.guardianReviewProviders).mockResolvedValue({ ready: false, selected: "mock", providers: { codex: { security_hold: true } } });
  vi.mocked(api.familyLocale).mockResolvedValue({ timezone: "America/New_York" });
  vi.mocked(api.notificationStatus).mockResolvedValue({ enabled: true, consent_allowed: true, worker_enabled: true, channels: { email: { configured: true, last_success_at: null }, webhook: { configured: false, last_success_at: null } }, counts: { queued: 0, retry: 0, processing: 0, sent: 0, dead: 0, skipped: 0 }, recent_jobs: [], recent_attempts: [], last_digest: null });
  vi.mocked(api.updateNotificationSettings).mockImplementation(async (body) => ({ ...body, password_configured: true }));
  vi.mocked(api.updateRetentionSettings).mockImplementation(async (body) => body);
  vi.mocked(api.updateBackupSettings).mockImplementation(async (body) => body);
  vi.mocked(api.updateFamilyLocale).mockImplementation(async (timezone) => ({ timezone }));
  vi.mocked(api.runRetentionCleanup).mockResolvedValue({});
  vi.mocked(api.runCompleteBackup).mockResolvedValue({});
});
afterEach(() => { cleanup(); clients.splice(0).forEach((client) => client.clear()); vi.resetAllMocks(); vi.restoreAllMocks(); });
describe("settings resilience", () => {
  it("surfaces an initial load failure and retries instead of staying on Loading forever", async () => {
    vi.mocked(api.storage).mockRejectedValueOnce(new Error("Storage unavailable"));
    show();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Storage unavailable"));
    expect(screen.queryByText("Loading settings…")).toBeNull();
    expect(screen.getByRole("button", { name: "Save notifications" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("SMTP host"), { target: { value: "unsaved.example.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Retry Storage" }));
    expect(await screen.findByRole("heading", { name: "Email alerts" })).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Retry Storage" })).toBeNull());
    expect(screen.getByLabelText("SMTP host")).toHaveProperty("value", "unsaved.example.test");
    expect(api.notificationSettings).toHaveBeenCalledTimes(1);
    expect(api.storage).toHaveBeenCalledTimes(2);
  });
  it("reports partial notification failure per channel without a false success banner", async () => {
    vi.mocked(api.testNotificationSettings).mockResolvedValue({ ok: false, detail: "partial", results: [{ channel: "email", ok: true, detail: "Accepted" }, { channel: "webhook", ok: false, detail: "Receiver unavailable" }] });
    show();
    const send = await screen.findByRole("button", { name: "Send test" });
    expect(api.testNotificationSettings).not.toHaveBeenCalled();
    fireEvent.click(send);
    expect(await screen.findByText("A notification test failed")).toBeTruthy();
    expect(screen.getByText("email: accepted")).toBeTruthy();
    expect(screen.getByText("webhook: failed")).toBeTruthy();
    expect(screen.queryByText("Test accepted by the configured channels")).toBeNull();
  });
});

describe("independent Settings drafts", () => {
  it("saving retention preserves notification, backup, and timezone drafts", async () => {
    show();
    await screen.findByRole("button", { name: "Save retention" });
    fireEvent.change(screen.getByLabelText("SMTP host"), { target: { value: "draft.smtp.test" } });
    fireEvent.change(screen.getByLabelText("Destination path"), { target: { value: "/draft-backup" } });
    fireEvent.change(screen.getByLabelText("Timezone (for example America/New_York)"), { target: { value: "Pacific/Auckland" } });
    fireEvent.change(screen.getByLabelText("high (days)"), { target: { value: "45" } });
    fireEvent.click(screen.getByRole("button", { name: "Save retention" }));
    await screen.findByText("Retention settings saved.");
    expect(api.updateRetentionSettings).toHaveBeenCalledWith(expect.objectContaining({ high: 45 }));
    expect(screen.getByLabelText("SMTP host")).toHaveProperty("value", "draft.smtp.test");
    expect(screen.getByLabelText("Destination path")).toHaveProperty("value", "/draft-backup");
    expect(screen.getByLabelText("Timezone (for example America/New_York)")).toHaveProperty("value", "Pacific/Auckland");
    expect(api.notificationSettings).toHaveBeenCalledTimes(1);
    expect(api.backupSettings).toHaveBeenCalledTimes(1);
    expect(api.familyLocale).toHaveBeenCalledTimes(1);
  });

  it("saving notifications preserves retention and clears only the saved secret draft", async () => {
    show();
    await screen.findByRole("button", { name: "Save notifications" });
    fireEvent.change(screen.getByLabelText("high (days)"), { target: { value: "44" } });
    fireEvent.change(screen.getByLabelText(/Password/), { target: { value: "new-app-password" } });
    fireEvent.change(screen.getByLabelText("Immediate alert threshold"), { target: { value: "medium" } });
    fireEvent.click(screen.getByRole("button", { name: "Save notifications" }));
    await screen.findByText("Notification settings saved.");
    expect(api.updateNotificationSettings).toHaveBeenCalledWith(expect.objectContaining({ password: "new-app-password", immediate_min_severity: "medium" }));
    expect(screen.getByLabelText("high (days)")).toHaveProperty("value", "44");
    expect(screen.getByLabelText(/password/i)).toHaveProperty("value", "");
    expect(screen.getByText(/Lowering it does not resend historical alerts/)).toBeTruthy();
  });

  it("renders independent initial failures and retries only the failed section", async () => {
    vi.mocked(api.notificationSettings).mockRejectedValueOnce(new Error("SMTP config unavailable"));
    vi.mocked(api.exports).mockRejectedValueOnce(new Error("Export inventory unavailable"));
    show();
    await screen.findByRole("button", { name: "Retry Email alerts" });
    expect(screen.getByRole("button", { name: "Retry Exports" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save retention" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("high (days)"), { target: { value: "42" } });
    fireEvent.click(screen.getByRole("button", { name: "Retry Email alerts" }));
    await screen.findByRole("button", { name: "Save notifications" });
    expect(screen.getByRole("button", { name: "Retry Exports" })).toBeTruthy();
    expect(screen.getByLabelText("high (days)")).toHaveProperty("value", "42");
    expect(api.retentionSettings).toHaveBeenCalledTimes(1);
    expect(api.exports).toHaveBeenCalledTimes(1);
  });

  it("keeps drafts after a save fails and allows retry", async () => {
    vi.mocked(api.updateRetentionSettings).mockRejectedValueOnce(new Error("Save unavailable"));
    show();
    await screen.findByRole("button", { name: "Save retention" });
    fireEvent.change(screen.getByLabelText("high (days)"), { target: { value: "41" } });
    fireEvent.click(screen.getByRole("button", { name: "Save retention" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Save unavailable");
    expect(screen.getByLabelText("high (days)")).toHaveProperty("value", "41");
    expect(screen.queryByText("Retention settings saved.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save retention" }));
    await screen.findByText("Retention settings saved.");
    expect(api.updateRetentionSettings).toHaveBeenLastCalledWith(expect.objectContaining({ high: 41 }));
  });

  it("refreshes backup run history without replacing an unsaved backup destination", async () => {
    vi.mocked(api.backupSettings).mockResolvedValue({ config: { enabled: true, destination: "/backup", retention_count: 7, interval_seconds: 86400 }, runs: [] });
    show();
    await screen.findByRole("button", { name: "Back up now" });
    fireEvent.change(screen.getByLabelText("Destination path"), { target: { value: "/draft-backup" } });
    fireEvent.click(screen.getByRole("button", { name: "Back up now" }));
    await screen.findByText("Complete backup created and verified.");
    expect(screen.getByLabelText("Destination path")).toHaveProperty("value", "/draft-backup");
    expect(api.backupSettings).toHaveBeenCalledTimes(2);
    expect(api.notificationSettings).toHaveBeenCalledTimes(1);
  });

  it("a successful cleanup with a failed status refresh reports stale totals without losing drafts", async () => {
    show();
    await screen.findByRole("button", { name: "Run cleanup" });
    fireEvent.change(screen.getByLabelText("SMTP host"), { target: { value: "draft.smtp.test" } });
    vi.mocked(api.storage).mockRejectedValueOnce(new Error("Counts unavailable"));
    fireEvent.click(screen.getByRole("button", { name: "Run cleanup" }));
    await screen.findByText("Cleanup completed.");
    expect(screen.getByRole("alert").textContent).toContain("Previously loaded totals may be out of date");
    expect(screen.getByLabelText("SMTP host")).toHaveProperty("value", "draft.smtp.test");
    expect(api.runRetentionCleanup).toHaveBeenCalledTimes(1);
  });
});


it("reports screenshot deletion counts without claiming every screenshot was wiped", async () => {
  vi.mocked(api.wipeStorage).mockResolvedValue({ ok: true, deleted: { blobs: 2 } });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Wipe screenshots" }));
  expect(await screen.findByText(/Screenshot deletion attempt finished: 2 retained files removed/)).toBeTruthy();
  expect(screen.queryByText("Screenshots wiped.")).toBeNull();
});
