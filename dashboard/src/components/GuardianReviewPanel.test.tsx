import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import GuardianReviewPanel from "./GuardianReviewPanel";
import { api } from "../api";

vi.mock("../api", () => ({
  api: {
    guardianReviewProviders: vi.fn(),
    guardianReviewHistory: vi.fn(),
    guardianReviewPreview: vi.fn(),
    cancelGuardianReviewPreview: vi.fn(),
    submitGuardianReview: vi.fn(),
    guardianReview: vi.fn(),
    deleteGuardianReview: vi.fn(),
  },
}));

const detail = {
  risk: { evidence: ["detector-selected excerpt"] },
  redacted_text: "additional full extracted screen text",
};

const provider = {
  enabled: true,
  ready: true,
  model: "gpt-5.6-sol",
  selected: "codex",
};

const preview = {
  preview_id: "preview-1",
  preview_digest: "a".repeat(64),
  model_requested: "gpt-5.6-sol",
  redaction_version: "guardian-review-redaction-v2",
  character_count: 120,
  information_categories: ["local_detector_findings"],
  disclosure: "This exact preview will be sent to an external OpenAI model.",
  retention_notice: "ChatGPT workspace data controls apply.",
  outbound_payload: { local_detector_findings: { severity: "medium" }, minimized_evidence: [] },
};

beforeEach(() => {
  vi.mocked(api.guardianReviewProviders).mockResolvedValue(provider);
  vi.mocked(api.guardianReviewHistory).mockResolvedValue([]);
  vi.mocked(api.guardianReviewPreview).mockResolvedValue(preview);
  vi.mocked(api.cancelGuardianReviewPreview).mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderPanel() {
  return render(<MemoryRouter><GuardianReviewPanel alertId="alert-1" detail={detail} /></MemoryRouter>);
}

describe("Guardian Review privacy flow", () => {
  it("stays disabled until the provider is configured", async () => {
    vi.mocked(api.guardianReviewProviders).mockResolvedValue({ ...provider, ready: false });
    renderPanel();
    expect(await screen.findByText("Not configured")).toBeTruthy();
    expect(screen.getByText(/stays disabled until/i)).toBeTruthy();
    expect(screen.queryByText("Preview what would be sent")).toBeNull();
  });

  it("lets the parent remove optional fields before generating the exact preview", async () => {
    renderPanel();
    await screen.findByText("gpt-5.6-sol ready");
    fireEvent.click(screen.getByLabelText("Include approximate age group"));
    fireEvent.click(screen.getByLabelText("Include selected minimized evidence"));
    fireEvent.click(screen.getByText("Preview what would be sent"));
    await waitFor(() => expect(api.guardianReviewPreview).toHaveBeenCalled());
    expect(vi.mocked(api.guardianReviewPreview).mock.calls[0][1]).toMatchObject({
      include_age_group: false,
      include_evidence: false,
      selected_evidence_ids: [],
    });
    expect(screen.getByTestId("guardian-review-outbound").textContent).toContain("local_detector_findings");
    expect(screen.getByText("Stored locally — not transmitted")).toBeTruthy();
    expect(screen.getByText("Sent to OpenAI if you continue")).toBeTruthy();
  });

  it("requires unchecked explicit consent and cancellation sends nothing", async () => {
    renderPanel();
    await screen.findByText("gpt-5.6-sol ready");
    fireEvent.click(screen.getByText("Preview what would be sent"));
    const send = await screen.findByText("Send for Guardian Review") as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.click(screen.getByText("Cancel — send nothing"));
    await waitFor(() => expect(api.cancelGuardianReviewPreview).toHaveBeenCalledWith("preview-1"));
    expect(api.submitGuardianReview).not.toHaveBeenCalled();
    expect(await screen.findByText("Preview what would be sent")).toBeTruthy();
  });

  it("submits only after consent and renders the structured result", async () => {
    vi.mocked(api.submitGuardianReview).mockResolvedValue({ review_id: "review-1", status: "queued" });
    vi.mocked(api.guardianReview).mockResolvedValue({
      review_id: "review-1", status: "completed", model_requested: "gpt-5.6-sol",
      model_returned: "gpt-5.6-sol", schema_version: "1.1.0", prompt_version: "guardian-review-v1",
      redaction_version: "guardian-review-redaction-v2",
      assessment: {
        assessment: "ambiguous", severity: "medium", plain_language_summary: "Context is incomplete.",
        observed_facts: ["A local detector found an excerpt."], possible_benign_explanations: ["It may be a quote."],
        missing_context: ["Who was involved."], suggested_opening_language: "Can you help me understand?",
        questions_to_ask_child: ["What happened?"], phrases_or_approaches_to_avoid: ["Avoid accusations."],
        escalation_indicators: ["Imminent danger."], limitations: ["This is a second opinion."],
      },
    });
    renderPanel();
    await screen.findByText("gpt-5.6-sol ready");
    fireEvent.click(screen.getByText("Preview what would be sent"));
    await screen.findByText("Send for Guardian Review");
    fireEvent.click(screen.getByLabelText(/I reviewed the exact content/i));
    fireEvent.click(screen.getByText("Send for Guardian Review"));
    expect(await screen.findByText("Context is incomplete.")).toBeTruthy();
    expect(api.submitGuardianReview).toHaveBeenCalledWith("alert-1", "preview-1", "a".repeat(64));
  });
});
