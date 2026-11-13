import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, type ChildRequest } from "../api";
import Requests from "./Requests";

vi.mock("../api", () => ({ api: { childRequests: vi.fn(), reviewChildRequest: vi.fn(), profiles: vi.fn(), devices: vi.fn() } }));
const clients: QueryClient[] = [];
const row: ChildRequest = { request_id: "request-1", device_id: "device-1", profile_id: "child-1", request_type: "more_time", target: "Homework", reason: "Finishing my project", status: "open", response_note: null, created_at: "2026-11-12T12:00:00Z", expires_at: "2026-11-19T12:00:00Z", reviewed_by: null, reviewed_at: null };
function show(seedHomeCache = false) { const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } }); if (seedHomeCache) client.setQueryData(["child-requests", "open"], { items: [row], next_cursor: null, open_count: 1 }); clients.push(client); render(<QueryClientProvider client={client}><Requests /></QueryClientProvider>); }
beforeEach(() => {
  vi.mocked(api.childRequests).mockResolvedValue({ items: [row], next_cursor: null, open_count: 1 });
  vi.mocked(api.devices).mockResolvedValue([{ device_id: "device-1", hostname: "Study laptop" } as never]);
  vi.mocked(api.profiles).mockResolvedValue([{ profile_id: "child-1", display_name: "Alex" } as never]);
  vi.mocked(api.reviewChildRequest).mockResolvedValue({ ...row, status: "approved" });
});
afterEach(() => { cleanup(); clients.splice(0).forEach((client) => client.clear()); vi.resetAllMocks(); });
describe("family request review", () => {
  it("keeps paginated history separate from the home dashboard query cache", async () => {
    show(true);
    expect(await screen.findByText("For: Homework")).toBeTruthy();
    expect(api.childRequests).toHaveBeenCalledWith({ limit: "50", status: "open" });
  });
  it("names the child/device and saves a parent response with the decision", async () => {
    show();
    const response = await screen.findByLabelText("Response to Alex · Study laptop (optional)");
    fireEvent.change(response, { target: { value: "Finish this task and check in at dinner." } });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(api.reviewChildRequest).toHaveBeenCalledWith("request-1", "approved", "Finish this task and check in at dinner."));
    expect(await screen.findByText("Your response was recorded. Any device or app change must be applied separately.")).toBeTruthy();
  });
  it("loads older requests using the selected status and server cursor", async () => {
    vi.mocked(api.childRequests).mockImplementation(async (params) => ({ items: params?.cursor ? [{ ...row, request_id: "request-2", target: "Older homework" }] : [row], next_cursor: params?.cursor ? null : "next-1", open_count: 2 }));
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Load older requests" }));
    expect(await screen.findByText("For: Older homework")).toBeTruthy();
    expect(api.childRequests).toHaveBeenCalledWith({ limit: "50", status: "open", cursor: "next-1" });
    fireEvent.change(screen.getByLabelText("Request status"), { target: { value: "denied" } });
    await waitFor(() => expect(api.childRequests).toHaveBeenLastCalledWith({ limit: "50", status: "denied" }));
  });
  it("shows the stored response for decided requests and no decision buttons", async () => {
    vi.mocked(api.childRequests).mockResolvedValue({ items: [{ ...row, status: "denied", response_note: "Let's revisit tomorrow." }], next_cursor: null, open_count: 0 });
    show();
    expect(await screen.findByText("Let's revisit tomorrow.", { exact: false })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });
});
