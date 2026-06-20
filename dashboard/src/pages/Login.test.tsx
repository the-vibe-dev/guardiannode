import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup, screen } from "@testing-library/react";
import Login from "./Login";

afterEach(cleanup);

describe("Login (mobile-safe layout)", () => {
  it("renders the sign-in form", () => {
    render(<Login onLogin={() => {}} />);
    expect(screen.getByText("GuardianNode")).toBeTruthy();
    expect(document.querySelector('input[type="password"]')).toBeTruthy();
  });

  it("constrains the card width and pads horizontally so it does not overflow on phones", () => {
    const { container } = render(<Login onLogin={() => {}} />);
    // Regression guard for the mobile-overflow fix: a bounded card inside a
    // horizontally-padded full-height wrapper.
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.className).toContain("px-4");
    const card = wrapper.querySelector(".max-w-md") as HTMLElement;
    expect(card).toBeTruthy();
    expect(card.className).toContain("w-full");
  });
});
