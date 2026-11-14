import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AssessmentResult } from "./GuardianReviewPanel";
import { api } from "../api";

vi.mock("../api", async (importOriginal) => ({
  ...await importOriginal<typeof import("../api")>(),
  api: { guardianReviewFeedback: vi.fn(), saveGuardianReviewFeedback: vi.fn() },
}));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

function result(id: string) {
  return { review_id: id, status: "completed", assessment: { assessment: "ambiguous", severity: "medium", plain_language_summary: `Assessment ${id}` } };
}

describe("review-specific feedback", () => {
  it("does not carry a previous assessment's labels into a newly selected result", async () => {
    let resolve!: (row: any) => void;
    const firstFeedback = new Promise((success) => { resolve = success; });
    vi.mocked(api.guardianReviewFeedback).mockImplementation((id) => id === "first" ? firstFeedback : Promise.resolve(null));
    vi.mocked(api.saveGuardianReviewFeedback).mockResolvedValue({ labels: ["missing_context"] });
    const view = render(<AssessmentResult result={result("first")} />);
    view.rerender(<AssessmentResult result={result("second")} />);
    await waitFor(() => expect((screen.getByLabelText("Helpful") as HTMLInputElement).disabled).toBe(false));
    await act(async () => { resolve({ labels: ["helpful"] }); await firstFeedback; });
    expect((screen.getByLabelText("Helpful") as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByLabelText("Missing context"));
    fireEvent.click(screen.getByRole("button", { name: "Save feedback" }));
    await waitFor(() => expect(api.saveGuardianReviewFeedback).toHaveBeenCalledWith("second", ["missing_context"]));
  });

  it("preserves unknown saved feedback until loading succeeds instead of silently overwriting it", async () => {
    vi.mocked(api.guardianReviewFeedback).mockRejectedValueOnce(new Error("Offline")).mockResolvedValueOnce({ labels: ["too_alarmist"] });
    render(<AssessmentResult result={result("first")} />);
    expect(await screen.findByRole("button", { name: "Retry feedback" })).toBeTruthy();
    expect((screen.getByRole("button", { name: "Save feedback" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("Helpful") as HTMLInputElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Retry feedback" }));
    await waitFor(() => expect((screen.getByLabelText("Too alarmist") as HTMLInputElement).checked).toBe(true));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(api.saveGuardianReviewFeedback).not.toHaveBeenCalled();
  });
});
