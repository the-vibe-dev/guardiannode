import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Layout from "./Layout";

afterEach(cleanup);

function renderLayout() {
  return render(
    <MemoryRouter>
      <Layout user={{ display_name: "Parent", role: "owner" }} onLogout={() => {}}>
        <div>content</div>
      </Layout>
    </MemoryRouter>
  );
}

describe("Layout responsive navigation", () => {
  it("renders every navigation destination", () => {
    renderLayout();
    for (const label of ["Home", "Alerts", "Children", "Devices", "Requests", "Privacy & consent", "Models", "Audit", "Review history", "Diagnostics & settings"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it("uses responsive breakpoint classes rather than a fixed desktop-only width", () => {
    const { container } = renderLayout();
    const aside = container.querySelector("aside")!;
    expect(aside).toBeTruthy();
    // Responsive: off-canvas on phones and a persistent sidebar at md+.
    expect(aside.className).toContain("md:");
    expect(aside.className).toContain("-translate-x-full");
    // Regression guard: no hard-coded fixed sidebar width without a breakpoint.
    expect(/(^|\s)w-(56|64)(\s|$)/.test(aside.className)).toBe(false);
    expect(screen.getByRole("button", { name: "Open navigation" })).toBeTruthy();
  });

  it("renders children content", () => {
    renderLayout();
    expect(screen.getByText("content")).toBeTruthy();
  });
});
