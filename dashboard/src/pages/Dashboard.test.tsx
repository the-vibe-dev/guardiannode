import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, type CaptureStatus, type CaptureDeviceStatus } from "../api";
import Dashboard from "./Dashboard";

vi.mock("../api", () => ({ api: { overview: vi.fn(), alerts: vi.fn(), devices: vi.fn(), profiles: vi.fn(), onboardingStatus: vi.fn(), me: vi.fn(), captureStatus: vi.fn() } }));
const clients: QueryClient[] = [];
const capture = (devices: CaptureDeviceStatus[] = []): CaptureStatus => ({ latest_capture_at: null, latest_capture_device_id: null, latest_capture_hostname: null, pending_review_count: 0, reviewing_count: 0, waiting_upload_count: 0, estimated_wait_seconds: null, last_reviewed_at: null, devices, review_failures_5m: 0 });
const device = (patch: Partial<CaptureDeviceStatus> = {}): CaptureDeviceStatus => ({ device_id: "device-1", hostname: "Alex's laptop", connection_status: "online", latest_capture_at: new Date().toISOString(), last_reviewed_at: new Date().toISOString(), last_review_status: "ai_reviewed", classifier_status: "ok", review_model: "local-vision", pending_review_count: 0, reviewing_count: 0, waiting_upload_count: null, queue_report_age_seconds: null, ...patch });

beforeEach(() => {
  vi.mocked(api.overview).mockResolvedValue({ counts_24h: { critical: 0, high: 0, medium: 0, low: 0 }, counts_7d: { critical: 0, high: 0, medium: 0, low: 0 }, open_alert_count: 0, devices_total: 1, devices_online: 1, devices_paused: 0, recent_severity_counts: {} });
  vi.mocked(api.alerts).mockResolvedValue({ items: [], next_cursor: null, open_count: 0 });
  vi.mocked(api.devices).mockResolvedValue([]);
  vi.mocked(api.profiles).mockResolvedValue([]);
  vi.mocked(api.onboardingStatus).mockResolvedValue({ complete: true, current_step: null, steps: [], checked_at: new Date().toISOString() });
  vi.mocked(api.me).mockResolvedValue({ display_name: "Parent", role: "admin" });
  vi.mocked(api.captureStatus).mockResolvedValue(capture());
});
afterEach(() => { cleanup(); clients.splice(0).forEach((client) => client.clear()); vi.resetAllMocks(); });
function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  clients.push(client);
  render(<QueryClientProvider client={client}><MemoryRouter><Dashboard /></MemoryRouter></QueryClientProvider>);
}

describe("screenshot review overview", () => {
  it("keeps empty alerts separate from successful capture and removes exception requests", async () => {
    show();
    expect(await screen.findByText("No captures received yet")).toBeTruthy();
    expect(screen.getByText(/empty alert feed does not confirm that every screen was reviewed/)).toBeTruthy();
    expect(screen.queryByText("Child requests")).toBeNull();
    expect(screen.queryByRole("link", { name: "Requests" })).toBeNull();
    expect(screen.queryByText("Recent capture reviewed")).toBeNull();
  });
  it("reports recent AI, stale review, and unknown upload backlog independently for each device", async () => {
    const old = new Date(Date.now() - 60 * 60_000).toISOString();
    vi.mocked(api.captureStatus).mockResolvedValue(capture([device(), device({ device_id: "device-2", hostname: "Offline desktop", connection_status: "offline", last_reviewed_at: old, last_review_status: "rules_only", review_model: "local-rules", classifier_status: "rules_only" })]));
    show();
    const ai = (await screen.findByRole("heading", { name: "Alex's laptop" })).closest("li")!;
    expect(within(ai).getByText("AI result recorded")).toBeTruthy();
    expect(within(ai).getByText(/Upload backlog unknown/)).toBeTruthy();
    const offline = screen.getByRole("heading", { name: "Offline desktop" }).closest("li")!;
    expect(within(offline).getByText("Rules only — AI review not confirmed")).toBeTruthy();
    expect(within(offline).getByText(/Over 10 minutes ago/)).toBeTruthy();
    expect(within(offline).getByRole("link", { name: "Check AI review setup" })).toBeTruthy();
  });
  it("shows captured-but-unreviewed and degraded states even when the server queue is empty", async () => {
    vi.mocked(api.captureStatus).mockResolvedValue({ ...capture([device({ last_reviewed_at: null, last_review_status: "not_reviewed", review_model: null }), device({ device_id: "device-2", hostname: "Second laptop", last_review_status: "degraded", classifier_status: "parse_error", review_model: null })]), review_failures_5m: 2 });
    show();
    expect(await screen.findByText("No completed review")).toBeTruthy();
    expect(screen.getByText("Review degraded — needs checking")).toBeTruthy();
    expect(screen.getByText("Classifier status: parse error")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("2 review failures recorded in the last 5 minutes");
    expect(screen.queryByText(/all.*safe/i)).toBeNull();
  });
  it("preserves other overview data when capture diagnostics fail and supports retry", async () => {
    vi.mocked(api.captureStatus).mockRejectedValueOnce(new Error("Offline")).mockResolvedValueOnce(capture());
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Retry capture status" }));
    expect(await screen.findByText("No captures received yet")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Needs your attention" })).toBeTruthy();
  });
  it("keeps available capture review diagnostics visible when the family overview fails", async () => {
    vi.mocked(api.overview).mockRejectedValue(new Error("Overview unavailable"));
    vi.mocked(api.captureStatus).mockResolvedValue(capture([device({ last_review_status: "degraded", review_model: null, classifier_status: "model_unavailable" })]));
    show();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Overview unavailable"));
    expect(await screen.findByText("Classifier status: model unavailable")).toBeTruthy();
    expect(screen.getByText("Review degraded — needs checking")).toBeTruthy();
  });
  it("labels monitoring pauses as capture privacy and does not imply the device is blocked", async () => {
    vi.mocked(api.captureStatus).mockResolvedValue(capture([device({ connection_status: "paused" })]));
    show();
    expect(await screen.findByText(/Screenshot capture is paused/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /block|limit/i })).toBeNull();
  });
});
