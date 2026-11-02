import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";
import { ChatPage } from "./chat-page";

const mocks = vi.hoisted(() => ({
  list: vi.fn(), create: vi.fn(), investigate: vi.fn(), messages: vi.fn(), remove: vi.fn(),
}));
vi.mock("../services/conversations", () => ({ conversationService: mocks }));

describe("ChatPage", () => {
  test("creates a conversation automatically for the first message", async () => {
    mocks.list.mockResolvedValue({ items: [] });
    mocks.messages.mockResolvedValue({ items: [] });
    mocks.create.mockResolvedValue({ id: "conversation-1", title: "New investigation", created_at: "", updated_at: "" });
    mocks.investigate.mockResolvedValue({ findings: "Evidence-based answer", error: null, data_sources: ["Prometheus Metrics"] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<MemoryRouter><QueryClientProvider client={client}><ChatPage /></QueryClientProvider></MemoryRouter>);

    const composer = await screen.findByRole("textbox", { name: /investigation question/i });
    fireEvent.change(composer, { target: { value: "Why is CPU high?" } });
    fireEvent.click(screen.getByRole("button", { name: /send investigation/i }));

    await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mocks.investigate).toHaveBeenCalledWith("conversation-1", "Why is CPU high?"));
  });
});
