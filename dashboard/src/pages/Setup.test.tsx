import { describe, it, expect, afterEach, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import Setup from "./Setup";
import { api } from "../api";

vi.mock("../api", () => ({
  api: {
    generateRecovery: vi.fn(),
    setup: vi.fn(),
    me: vi.fn(),
  },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Setup", () => {
  it("loads the current user before completing setup", async () => {
    vi.mocked(api.generateRecovery).mockResolvedValue({
      words: ["one", "two", "three", "four"],
      code: "one two three four",
      word_count: 4,
    });
    vi.mocked(api.setup).mockResolvedValue({ ok: true });
    vi.mocked(api.me).mockResolvedValue({ display_name: "Parent", role: "admin" });
    const onComplete = vi.fn();

    render(<Setup onComplete={onComplete} />);

    fireEvent.change(screen.getByLabelText(/one-time setup token/i), { target: { value: "setup-token" } });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.change(screen.getByLabelText(/^Password/i), { target: { value: "correct-horse" } });
    fireEvent.change(screen.getByLabelText(/Confirm password/i), { target: { value: "correct-horse" } });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(api.generateRecovery).toHaveBeenCalledWith("setup-token"));

    fireEvent.click(screen.getByLabelText(/written down/i));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Finish" }));

    await waitFor(() => expect(api.me).toHaveBeenCalled());
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1600));
    });

    expect(onComplete).toHaveBeenCalledWith({ display_name: "Parent", role: "admin" });
  }, 8000);
});
