import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Devices from "./Devices";
import { api, type Device } from "../api";

vi.mock("../api", () => ({ api: { devices: vi.fn(), profiles: vi.fn(), pauseDevice: vi.fn(), resumeDevice: vi.fn(), assignDeviceProfile: vi.fn(), startPair: vi.fn(), revokeDevice: vi.fn() } }));
const clients: QueryClient[] = [];
function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  clients.push(client);
  return render(<QueryClientProvider client={client}><Devices /></QueryClientProvider>);
}
function device(status = "online"): Device {
  return { device_id: "computer-1", hostname: "Child PC", profile_id: "child-1", status, last_seen: "2026-11-14T12:00:00Z" } as Device;
}
afterEach(() => { cleanup(); clients.splice(0).forEach((client) => client.clear()); vi.resetAllMocks(); vi.useRealTimers(); });

describe("device capture status", () => {
  it("does not present pending or failed device loads as an empty family", async () => {
    vi.mocked(api.devices).mockRejectedValueOnce(new Error("Server unavailable")).mockResolvedValueOnce([]);
    vi.mocked(api.profiles).mockResolvedValue([]);
    show();
    expect(screen.getByRole("status").textContent).toContain("Loading paired devices");
    expect(screen.queryByText("No devices paired yet")).toBeNull();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Server unavailable"));
    expect(screen.queryByText("No devices paired yet")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry devices" }));
    expect(await screen.findByText("No devices paired yet")).toBeTruthy();
  });

  it("preserves an assigned child's identity and disables changes if profile loading fails", async () => {
    vi.mocked(api.devices).mockResolvedValue([device()]);
    vi.mocked(api.profiles).mockRejectedValueOnce(new Error("Profile service unavailable")).mockResolvedValueOnce([{ profile_id: "child-1", display_name: "Jamie" } as any]);
    show();
    const retry = await screen.findByRole("button", { name: "Retry profiles" });
    for (const select of screen.getAllByRole("combobox", { name: "Child profile for Child PC" })) {
      expect((select as HTMLSelectElement).value).toBe("child-1");
      expect((select as HTMLSelectElement).disabled).toBe(true);
    }
    fireEvent.click(retry);
    await waitFor(() => expect(screen.getAllByRole("option", { name: "Jamie" })).toHaveLength(2));
    expect((screen.getAllByRole("combobox", { name: "Child profile for Child PC" })[0] as HTMLSelectElement).disabled).toBe(false);
    expect(api.assignDeviceProfile).not.toHaveBeenCalled();
  });

  it("refreshes device status while the page remains open", async () => {
    vi.mocked(api.devices).mockResolvedValueOnce([device()]).mockResolvedValue([device("paused")]);
    vi.mocked(api.profiles).mockResolvedValue([]);
    vi.useFakeTimers();
    show();
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    expect(screen.getAllByRole("button", { name: "Pause screenshots" })).toHaveLength(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(15_100); });
    expect(screen.getAllByRole("button", { name: "Resume screenshots" })).toHaveLength(2);
    expect(api.devices).toHaveBeenCalledTimes(2);
    expect(api.pauseDevice).not.toHaveBeenCalled();
  });
});
