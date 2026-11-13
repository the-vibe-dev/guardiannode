import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "../api";
import ModelStatus from "./ModelStatus";

vi.mock("../api", () => ({ api: { modelStatus: vi.fn(), testModel: vi.fn() } }));
const clients: QueryClient[] = [];
const status = { tier: "text_only", tier_info: { label: "Text review", detects_images: false, detects_text: true, summary: "Extracted text" }, ollama_url: "http://localhost:11434", ollama_available: true, models_installed: ["text-model"], text_model: "text-model", vision_model: "vision-model" };
afterEach(() => { cleanup(); clients.splice(0).forEach((client) => client.clear()); vi.resetAllMocks(); });
function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  clients.push(client);
  render(<QueryClientProvider client={client}><ModelStatus /></QueryClientProvider>);
}
describe("AI review diagnostics", () => {
  it("recovers from model status failure without leaving an endless loading state", async () => {
    vi.mocked(api.modelStatus).mockRejectedValueOnce(new Error("Offline")).mockResolvedValueOnce(status);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Retry model status" }));
    expect(await screen.findByText("Text review")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText(/configured mode reviews extracted text/)).toBeTruthy();
  });
  it("shows text test failures explicitly and does not claim a successful screenshot test", async () => {
    vi.mocked(api.modelStatus).mockResolvedValue(status);
    vi.mocked(api.testModel).mockRejectedValueOnce(new Error("Classifier unavailable"));
    show();
    fireEvent.click(screen.getByRole("button", { name: "Run text test" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("No successful result was recorded"));
    expect(screen.getByText(/does not test screenshot capture, OCR, or vision accuracy/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Synthetic test text"), { target: { value: "Another synthetic test" } });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
