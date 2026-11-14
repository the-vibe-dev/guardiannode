import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError, api } from "../api";
import AlertDetail from "./AlertDetail";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, api: { alert: vi.fn(), confirmedAlertAction: vi.fn(), reviewAlert: vi.fn(), feedbackAlert: vi.fn() } };
});
vi.mock("../components/GuardianReviewPanel", () => ({ default: () => <div>Review panel</div> }));
vi.mock("../components/ActionHistory", () => ({ default: () => <div>Action history</div> }));
const clients: QueryClient[] = [];
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((success, failure) => { resolve = success; reject = failure; });
  return { promise, resolve, reject };
}
function detail(id: string) {
  return { alert: { alert_id: id, risk_id: `risk-${id}`, severity: "low", status: "open" }, risk: { risk_id: `risk-${id}`, summary: `Evidence for ${id}`, score: 10, confidence: 1, categories: [], evidence: [], rules_triggered: [] }, event: { event_id: null }, redacted_text: null };
}
function Navigate() { const navigate = useNavigate(); return <button onClick={() => navigate("/alerts/current")}>Next alert</button>; }
function show() { const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }); clients.push(client); render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/alerts/previous"]}><Navigate /><Routes><Route path="/alerts/:id" element={<AlertDetail />} /></Routes></MemoryRouter></QueryClientProvider>); }
afterEach(() => { cleanup(); clients.splice(0).forEach((client) => client.clear()); vi.resetAllMocks(); });
describe("incident route isolation", () => {
  it("ignores a slow previous alert response after navigating to another incident", async () => {
    const previous = deferred<ReturnType<typeof detail>>();
    vi.mocked(api.alert).mockImplementation((id) => id === "previous" ? previous.promise : Promise.resolve(detail(id)));
    show();
    fireEvent.click(screen.getByRole("button", { name: "Next alert" }));
    expect(await screen.findByText("Evidence for current")).toBeTruthy();
    await act(async () => { previous.resolve(detail("previous")); await previous.promise; });
    expect(screen.getByText("Evidence for current")).toBeTruthy();
    expect(screen.queryByText("Evidence for previous")).toBeNull();
  });
  it("removes old evidence immediately and does not carry notes into the next alert", async () => {
    const current = deferred<ReturnType<typeof detail>>();
    vi.mocked(api.alert).mockImplementation((id) => id === "current" ? current.promise : Promise.resolve(detail(id)));
    show();
    await screen.findByText("Evidence for previous");
    fireEvent.change(screen.getByPlaceholderText("Optional notes…"), { target: { value: "Notes for previous incident" } });
    fireEvent.click(screen.getByRole("button", { name: "Next alert" }));
    expect(screen.queryByText("Evidence for previous")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Loading…");
    await act(async () => { current.resolve(detail("current")); await current.promise; });
    expect((screen.getByPlaceholderText("Optional notes…") as HTMLTextAreaElement).value).toBe("");
  });
  it("ignores an old route's failure after the current alert has loaded", async () => {
    const previous = deferred<ReturnType<typeof detail>>();
    vi.mocked(api.alert).mockImplementation((id) => id === "previous" ? previous.promise : Promise.resolve(detail(id)));
    show();
    fireEvent.click(screen.getByRole("button", { name: "Next alert" }));
    await screen.findByText("Evidence for current");
    await act(async () => { previous.reject(new Error("Old request failed")); await previous.promise.catch(() => undefined); });
    expect(screen.queryByText("Old request failed")).toBeNull();
    expect(screen.getByText("Evidence for current")).toBeTruthy();
  });
});

describe("screenshot review focus", () => {
  it("offers evidence controls without restriction or child-notice controls", async () => {
    vi.mocked(api.alert).mockResolvedValue(detail("previous"));
    show();
    expect(await screen.findByRole("button", { name: "Preview evidence deletion…" })).toBeTruthy();
    expect(screen.queryByLabelText("Action")).toBeNull();
    expect(screen.queryByLabelText("Duration")).toBeNull();
    expect(screen.queryByLabelText("Child-facing message")).toBeNull();
    expect(screen.queryByText(/Parent-confirmed device action/)).toBeNull();
  });
  it("uses retained screenshot availability instead of severity to show reveal controls", async () => {
    const low = detail("previous");
    vi.mocked(api.alert).mockResolvedValue({ ...low, event: { event_id: "frame-1", has_screenshot: true, screenshot_status: "available" } });
    show();
    expect(await screen.findByRole("button", { name: "Reveal screenshot" })).toBeTruthy();
    expect(screen.queryByRole("img", { name: "Captured screenshot" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Reveal screenshot" }));
    expect(screen.getByRole("img", { name: "Captured screenshot" }).getAttribute("src")).toBe("/api/events/frame-1/screenshot");
    fireEvent.error(screen.getByRole("img", { name: "Captured screenshot" }));
    expect(screen.getByRole("alert").textContent).toContain("screenshot could not be loaded");
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    fireEvent.click(screen.getByRole("button", { name: "Reveal screenshot" }));
    fireEvent.load(screen.getByRole("img", { name: "Captured screenshot" }));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText("Loading retained screenshot…")).toBeNull();
  });
  it("distinguishes missing screenshot data from an unflagged or text-only result", async () => {
    vi.mocked(api.alert).mockResolvedValue({ ...detail("previous"), event: { event_id: "frame-1", has_screenshot: false, screenshot_status: "missing" } });
    show();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("image is unavailable"));
    expect(screen.queryByRole("button", { name: "Reveal screenshot" })).toBeNull();
  });
  it("unmounts evidence after confirmed deletion and shows its receipt without stale readback", async () => {
    vi.mocked(api.alert).mockResolvedValue({ ...detail("previous"), event: { event_id: "frame-1", has_screenshot: true, screenshot_status: "available" } });
    const preview = "Delete retained evidence for this alert";
    vi.mocked(api.confirmedAlertAction)
      .mockRejectedValueOnce(new ApiError("Confirmation required", 409, { detail: { preview } }))
      .mockResolvedValueOnce({ action_id: "delete-1", status: "completed" } as any);
    const confirmation = vi.spyOn(window, "confirm").mockReturnValue(true);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Reveal screenshot" }));
    fireEvent.click(screen.getByRole("button", { name: "Preview evidence deletion…" }));
    expect(await screen.findByText("The retained evidence for this alert has been deleted.")).toBeTruthy();
    expect(api.confirmedAlertAction).toHaveBeenLastCalledWith("previous", { action: "delete_evidence", confirmed_preview: preview, expected_risk_id: "risk-previous" });
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByText("Evidence for previous")).toBeNull();
    expect(api.alert).toHaveBeenCalledTimes(1);
    confirmation.mockRestore();
  });

  it.each([ ["Mark reviewed", "reviewAlert", "reviewed"], ["Confirm useful", "feedbackAlert", "confirmed"] ] as const)("binds %s to visible evidence and requires another decision after a conflict", async (label, method, value) => {
    const refreshed = deferred<any>();
    vi.mocked(api.alert).mockResolvedValueOnce({ ...detail("previous"), event: { event_id: "frame-1", has_screenshot: true } }).mockReturnValueOnce(refreshed.promise);
    vi.mocked(api[method]).mockRejectedValueOnce(new ApiError("Evidence changed", 409, { detail: { code: "evidence_changed" } }));
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Reveal screenshot" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Review notes" }), { target: { value: "Draft parent context" } });
    fireEvent.click(screen.getByRole("button", { name: label }));
    await waitFor(() => expect(api[method]).toHaveBeenCalledWith("previous", value, "Draft parent context", "risk-previous"));
    await waitFor(() => expect(screen.queryByRole("img")).toBeNull());
    const next = { ...detail("updated"), alert: { ...detail("updated").alert, alert_id: "previous" }, event: { event_id: "frame-2", has_screenshot: true } };
    await act(async () => { refreshed.resolve(next); await refreshed.promise; });
    expect(await screen.findByText("Evidence for updated")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("previous action was not applied");
    expect((screen.getByRole("textbox", { name: "Review notes" }) as HTMLTextAreaElement).value).toBe("Draft parent context");
    expect(screen.getByRole("button", { name: "Reveal screenshot" })).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
    expect(api[method]).toHaveBeenCalledTimes(1);
  });

  it("does not ask for deletion confirmation or replay deletion on an evidence conflict", async () => {
    vi.mocked(api.alert).mockResolvedValueOnce(detail("previous")).mockResolvedValueOnce(detail("updated"));
    vi.mocked(api.confirmedAlertAction).mockRejectedValueOnce(new ApiError("Evidence changed", 409, { detail: { code: "evidence_changed" } }));
    const confirmation = vi.spyOn(window, "confirm");
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Preview evidence deletion…" }));
    expect(await screen.findByText("Evidence for updated")).toBeTruthy();
    expect(confirmation).not.toHaveBeenCalled();
    expect(api.confirmedAlertAction).toHaveBeenCalledTimes(1);
    confirmation.mockRestore();
  });
});
