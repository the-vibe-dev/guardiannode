import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "../api";
import AlertDetail from "./AlertDetail";

vi.mock("../api", () => ({ api: { alert: vi.fn() }, ApiError: class extends Error {} }));
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
  return { alert: { alert_id: id, severity: "low", status: "open" }, risk: { summary: `Evidence for ${id}`, score: 10, confidence: 1, categories: [], evidence: [], rules_triggered: [] }, event: { event_id: null }, redacted_text: null };
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
  it("removes old evidence immediately and does not carry notes or action targets into the next alert", async () => {
    const current = deferred<ReturnType<typeof detail>>();
    vi.mocked(api.alert).mockImplementation((id) => id === "current" ? current.promise : Promise.resolve(detail(id)));
    show();
    await screen.findByText("Evidence for previous");
    fireEvent.change(screen.getByPlaceholderText("Optional notes…"), { target: { value: "Notes for previous incident" } });
    fireEvent.change(screen.getByLabelText("Child-facing message"), { target: { value: "Message for previous child" } });
    fireEvent.click(screen.getByRole("button", { name: "Next alert" }));
    expect(screen.queryByText("Evidence for previous")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Loading…");
    await act(async () => { current.resolve(detail("current")); await current.promise; });
    expect((screen.getByPlaceholderText("Optional notes…") as HTMLTextAreaElement).value).toBe("");
    expect((screen.getByLabelText("Child-facing message") as HTMLTextAreaElement).value).toBe("");
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
