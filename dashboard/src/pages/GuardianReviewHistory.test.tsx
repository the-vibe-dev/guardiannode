import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import GuardianReviewHistory from "./GuardianReviewHistory";
import { api } from "../api";

vi.mock("../api", () => ({ api: {
  guardianReviewHistory: vi.fn(), guardianReview: vi.fn(), deleteGuardianReview: vi.fn(),
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
});
