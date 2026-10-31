import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { api } from "../api";
import { requestStepUp } from "../stepUp";
import StepUpDialog from "./StepUpDialog";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function mount() {
  vi.stubGlobal("HTMLDialogElement", HTMLDialogElement);
  HTMLDialogElement.prototype.showModal = vi.fn();
  HTMLDialogElement.prototype.close = vi.fn();
  return render(<StepUpDialog />);
}

it("masks the password and resumes concurrent actions only after successful reauth", async () => {
  mount();
  const reauth = vi.spyOn(api, "reauth").mockResolvedValue({ ok: true });
  let first!: Promise<void>;
  let second!: Promise<void>;
  await act(async () => {
    first = requestStepUp("critical");
    second = requestStepUp("standard");
  });
  expect(first).toBe(second);
  const input = screen.getByLabelText("Parent password") as HTMLInputElement;
  expect(input.type).toBe("password");
  expect(input.autocomplete).toBe("current-password");
  fireEvent.change(input, { target: { value: "synthetic-password" } });
  fireEvent.click(screen.getByText("Continue"));
  await first;
  await waitFor(() => expect(reauth).toHaveBeenCalledOnce());
  expect(reauth).toHaveBeenCalledWith("synthetic-password");
});

it("cancels without reauthenticating", async () => {
  mount();
  const reauth = vi.spyOn(api, "reauth");
  let pending!: Promise<void>;
  await act(async () => { pending = requestStepUp("standard"); });
  fireEvent.click(screen.getByText("Cancel"));
  await expect(pending).rejects.toThrow("cancelled");
  expect(reauth).not.toHaveBeenCalled();
});
