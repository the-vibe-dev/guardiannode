import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { api } from "../api";
import Profiles from "./Profiles";

vi.mock("../api", () => ({ api: { profiles: vi.fn(), policyMeta: vi.fn(), createProfile: vi.fn(), updateProfile: vi.fn() } }));
const profile = { profile_id: "child-1", display_name: "Alex", age_group: "10_13", created_at: "2026-11-12T12:00:00Z", notes: null, custom_watch_phrases: ["School"], alert_policy: { min_severity: "critical", capture: { level: "leeway" }, categories: {} } };
beforeEach(() => {
  vi.mocked(api.profiles).mockResolvedValue([profile]);
  vi.mocked(api.policyMeta).mockResolvedValue({ severities: ["low", "medium", "high", "critical"], capture_levels: ["tight", "balanced", "leeway"], modes: ["alert", "monitor", "allow"], tunable_categories: [{ key: "scam", label: "Scams" }], protected_categories: ["self_harm", "grooming", "threat"] });
});
afterEach(() => { cleanup(); vi.resetAllMocks(); });
describe("profile policy editing", () => {
  it("updates visible policy controls with the server age defaults after reset", async () => {
    vi.mocked(api.updateProfile).mockResolvedValue({ ...profile, alert_policy: { min_severity: "medium", capture: { level: "balanced" }, categories: {} } });
    render(<Profiles />);
    fireEvent.click(await screen.findByRole("button", { name: /Privacy & alert settings/ }));
    const level = screen.getByLabelText("Only alert me at or above") as HTMLSelectElement;
    expect(level.value).toBe("critical");
    fireEvent.click(screen.getByRole("button", { name: "Reset to age defaults" }));
    await waitFor(() => expect(level.value).toBe("medium"));
    expect((screen.getByLabelText("How much to capture") as HTMLSelectElement).value).toBe("balanced");
    expect(api.updateProfile).toHaveBeenCalledWith("child-1", { reset_policy_to_age_default: true });
  });
  it("shows a policy save failure and keeps the draft editable", async () => {
    vi.mocked(api.updateProfile).mockRejectedValue(new Error("Connection lost"));
    render(<Profiles />);
    fireEvent.click(await screen.findByRole("button", { name: /Privacy & alert settings/ }));
    fireEvent.change(screen.getByLabelText("Only alert me at or above"), { target: { value: "high" } });
    fireEvent.click(screen.getByRole("button", { name: "Save privacy settings" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Connection lost");
    expect((screen.getByLabelText("Only alert me at or above") as HTMLSelectElement).value).toBe("high");
    expect((screen.getByRole("button", { name: "Save privacy settings" }) as HTMLButtonElement).disabled).toBe(false);
  });
});
