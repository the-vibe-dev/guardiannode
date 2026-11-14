import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import GuardianReviewHistory from "./GuardianReviewHistory";
import { api } from "../api";

vi.mock("../api", () => ({ api: {
  guardianReviewHistory: vi.fn(), guardianReview: vi.fn(), deleteGuardianReview: vi.fn(),
  guardianReviewFeedback: vi.fn().mockResolvedValue(null), saveGuardianReviewFeedback: vi.fn(),
} }));

afterEach(() => { cleanup(); vi.clearAllMocks(); vi.restoreAllMocks(); });

describe("Guardian Review global history", () => {
  it("shows privacy versions and scrubs a local assessment after confirmation", async () => {
    const row = {
      review_id: "review-1", alert_id: "alert-1", status: "completed", created_at: "2026-07-15T12:00:00Z",
      model_requested: "gpt-5.6", model_returned: "gpt-5.6-2026-07-01", schema_version: "1.1.0",
      prompt_version: "guardian-review-v1", redaction_version: "guardian-review-redaction-v2",
    };
    vi.mocked(api.guardianReviewHistory).mockResolvedValue([row]);
    vi.mocked(api.deleteGuardianReview).mockResolvedValue({ ...row, status: "deleted" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MemoryRouter><GuardianReviewHistory /></MemoryRouter>);
    expect(await screen.findByText("gpt-5.6-2026-07-01")).toBeTruthy();
    expect(document.body.textContent).toContain("guardian-review-redaction-v2");
    fireEvent.click(screen.getByText("Delete local assessment"));
    await waitFor(() => expect(api.deleteGuardianReview).toHaveBeenCalledWith("review-1"));
  });

  it("shows a retryable load failure without claiming history is empty", async () => {
    vi.mocked(api.guardianReviewHistory).mockRejectedValueOnce(new Error("Connection interrupted")).mockResolvedValueOnce([]);
    render(<MemoryRouter><GuardianReviewHistory /></MemoryRouter>);
    expect(screen.queryByText("No Guardian Reviews found.")).toBeNull();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Connection interrupted"));
    expect(screen.queryByText("No Guardian Reviews found.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry history" }));
    expect(await screen.findByText("No Guardian Reviews found.")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does not let a slower previously selected review replace the current one", async () => {
    const previous = deferred<any>();
    vi.mocked(api.guardianReviewHistory).mockResolvedValue([row("older"), row("newer")]);
    vi.mocked(api.guardianReview).mockImplementation((id) => id === "older" ? previous.promise : Promise.resolve(assessment("newer")));
    render(<MemoryRouter><GuardianReviewHistory /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "View review older" }));
    fireEvent.click(screen.getByRole("button", { name: "View review newer" }));
    expect(await screen.findByText("Private assessment newer")).toBeTruthy();
    await act(async () => { previous.resolve(assessment("older")); await previous.promise; });
    expect(screen.queryByText("Private assessment older")).toBeNull();
    expect(screen.getByText("Private assessment newer")).toBeTruthy();
  });

  it("clears a deleted assessment even if refreshing history fails", async () => {
    vi.mocked(api.guardianReviewHistory).mockResolvedValueOnce([row("private")]).mockRejectedValueOnce(new Error("History unavailable"));
    vi.mocked(api.guardianReview).mockResolvedValue(assessment("private"));
    vi.mocked(api.deleteGuardianReview).mockResolvedValue({ review_id: "private", status: "deleted" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MemoryRouter><GuardianReviewHistory /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /^View(?: review private)?$/ }));
    await screen.findByText("Private assessment private");
    fireEvent.click(screen.getByRole("button", { name: /^Delete local assessment(?: private)?$/ }));
    expect(await screen.findByText(/assessment and its outbound preview were deleted/)).toBeTruthy();
    expect(screen.queryByText("Private assessment private")).toBeNull();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("History unavailable"));
    expect(api.guardianReview).toHaveBeenCalledTimes(1);
  });

  it("cannot restore deleted content from an already pending detail response", async () => {
    const pending = deferred<any>();
    vi.mocked(api.guardianReviewHistory).mockResolvedValue([row("private")]);
    vi.mocked(api.guardianReview).mockReturnValue(pending.promise);
    vi.mocked(api.deleteGuardianReview).mockResolvedValue({ review_id: "private", status: "deleted" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MemoryRouter><GuardianReviewHistory /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /^View(?: review private)?$/ }));
    fireEvent.click(screen.getByRole("button", { name: /^Delete local assessment(?: private)?$/ }));
    await screen.findByText(/assessment and its outbound preview were deleted/);
    await act(async () => { pending.resolve(assessment("private")); await pending.promise; });
    expect(screen.queryByText("Private assessment private")).toBeNull();
    expect(screen.getByText(/assessment and its outbound preview were deleted/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Delete local assessment(?: private)?$/ })).toBeNull();
  });

  it("ignores an older filter response when a newer filter has completed", async () => {
    const all = deferred<any[]>();
    vi.mocked(api.guardianReviewHistory).mockImplementation((params) => params?.status === "failed" ? Promise.resolve([{ ...row("failed-only"), status: "failed" }]) : all.promise);
    render(<MemoryRouter><GuardianReviewHistory /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "failed" } });
    await screen.findByRole("button", { name: "View review failed-only" });
    await act(async () => { all.resolve([row("unfiltered")]); await all.promise; });
    expect(screen.queryByRole("button", { name: "View review unfiltered" })).toBeNull();
    expect(screen.getByRole("button", { name: "View review failed-only" })).toBeTruthy();
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((success) => { resolve = success; });
  return { promise, resolve };
}

function row(id: string) {
  return { review_id: id, alert_id: `alert-${id}`, status: "completed", created_at: "2026-07-15T12:00:00Z", model_requested: "model", schema_version: "1.1", prompt_version: "v2", redaction_version: "v3" };
}

function assessment(id: string) {
  return { ...row(id), assessment: { assessment: "ambiguous", severity: "medium", plain_language_summary: `Private assessment ${id}` } };
}
