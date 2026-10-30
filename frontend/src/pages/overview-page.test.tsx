import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { OverviewPage } from "./overview-page";

vi.mock("../services/monitoring", () => ({ monitoringService: { summary: vi.fn().mockRejectedValue(new Error("unavailable")) } }));

describe("OverviewPage", () => {
  test("does not claim infrastructure health when monitoring is unavailable", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><OverviewPage /></QueryClientProvider>);
    expect(await screen.findByText(/not claiming the infrastructure is healthy/i)).toBeTruthy();
  });
});
