import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, type ConsentStatus } from "../api";
import PrivacyConsent from "./PrivacyConsent";

vi.mock("../api", () => ({ api: { consentStatus: vi.fn(), grantConsent: vi.fn(), withdrawConsent: vi.fn() } }));
const clients: QueryClient[] = [];
const choices = { screenshots: true, apps_and_urls: true, retention: true, notifications: true, external_ai: false, child_notice_acknowledged: true };
const consent = { notice_version: "review-v1", active: true, record: { consent_id: "consent-1", notice_version: "review-v1", status: "granted", choices, created_at: "2026-11-12T12:00:00Z" } };
function show() { const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }); clients.push(client); render(<QueryClientProvider client={client}><PrivacyConsent /></QueryClientProvider>); }
beforeEach(() => { vi.mocked(api.consentStatus).mockResolvedValue(consent); vi.mocked(api.grantConsent).mockResolvedValue(consent); });
afterEach(() => { cleanup(); clients.splice(0).forEach((client) => client.clear()); vi.resetAllMocks(); vi.restoreAllMocks(); });
describe("privacy choice consequences", () => {
  it("explains and saves history-disabled monitoring pause without silently enabling external AI", async () => {
    show();
    const history = await screen.findByRole("checkbox", { name: /Keep alert history/ });
    fireEvent.click(history);
    expect(screen.getByText(/Saving with alert history disabled pauses new monitoring/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Update choices" }));
    await waitFor(() => expect(api.grantConsent).toHaveBeenCalledWith("review-v1", { ...choices, retention: false }));
    expect(await screen.findByText("Privacy choices saved.")).toBeTruthy();
  });
  it("shows saved monitoring pause and explains metadata and external-review limits", async () => {
    vi.mocked(api.consentStatus).mockResolvedValue({ ...consent, record: { ...consent.record, choices: { ...choices, retention: false } } });
    show();
    expect(await screen.findByText("Privacy choices saved; new monitoring is paused")).toBeTruthy();
    expect(screen.getByText(/screenshots and OCR may still contain visible context/)).toBeTruthy();
    expect(screen.getByText(/both required for every external review/)).toBeTruthy();
    expect(api.withdrawConsent).not.toHaveBeenCalled();
  });
});


describe("withdrawal deletion outcomes", () => {
  it("shows partial queued-file deletion and permits a retry after consent becomes inactive", async () => {
    let saved: ConsentStatus = consent;
    let attempts = 0;
    vi.mocked(api.consentStatus).mockImplementation(async () => saved);
    vi.mocked(api.withdrawConsent).mockImplementation(async () => {
      attempts += 1;
      saved = { ...consent, active: false, record: { ...consent.record, status: "withdrawn", choices: { evidence_disposition: "delete" } } };
      return { ...saved, deletion: { events: attempts === 1 ? 4 : 0, blobs: 2, remaining_events: 0, remaining_blobs: 0, pending_captures: { deleted: 3, failed: attempts === 1 ? 1 : 0 } } };
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Withdraw and delete evidence…" }));
    expect(await screen.findByText("Monitoring stopped; some evidence still needs deletion.")).toBeTruthy();
    expect(screen.getByText("Queued capture cleanup reported 1 failure. Some queued files may remain.")).toBeTruthy();
    expect(screen.getByText("Backups, existing exports and downloaded copies are not included.")).toBeTruthy();
    const retry = await screen.findByRole("button", { name: "Retry evidence deletion…" });
    expect(screen.queryByRole("button", { name: "Withdraw and delete evidence…" })).toBeNull();
    fireEvent.click(retry);
    expect(await screen.findByText("Monitoring stopped. Deletion attempt finished.")).toBeTruthy();
    expect(screen.queryByText("Queued capture cleanup reported 1 failure. Some queued files may remain.")).toBeNull();
    expect(api.withdrawConsent).toHaveBeenCalledTimes(2);
    expect(api.withdrawConsent).toHaveBeenNthCalledWith(2, "delete");
    expect(api.grantConsent).not.toHaveBeenCalled();
  });
  it("permits deleting retained evidence after loading an already-withdrawn consent record", async () => {
    const inactive: ConsentStatus = { ...consent, active: false, record: { ...consent.record, status: "withdrawn", choices: { evidence_disposition: "retain" } } };
    vi.mocked(api.consentStatus).mockResolvedValue(inactive);
    vi.mocked(api.withdrawConsent).mockResolvedValue({ ...inactive, deletion: { events: 0, blobs: 0, remaining_events: 0, remaining_blobs: 0, pending_captures: { deleted: 0, failed: 0 } } });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Delete remaining evidence…" }));
    await waitFor(() => expect(api.withdrawConsent).toHaveBeenCalledWith("delete"));
    expect(api.grantConsent).not.toHaveBeenCalled();
  });
  it("reports retained-evidence failures even when all queued captures were removed", async () => {
    vi.mocked(api.withdrawConsent).mockResolvedValue({ ...consent, active: false, deletion: { events: 2, blobs: 1, remaining_events: 1, remaining_blobs: 1, pending_captures: { deleted: 2, failed: 0 } } });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Withdraw and delete evidence…" }));
    expect(await screen.findByText("Monitoring stopped; some evidence still needs deletion.")).toBeTruthy();
    expect(screen.getByText("Remaining: 1 event records and 1 retained evidence files.")).toBeTruthy();
    expect(screen.queryByText("Monitoring stopped. Deletion attempt finished.")).toBeNull();
  });
});
