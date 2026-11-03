import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InfrastructurePage } from "./infrastructure-page";
import * as monitoringService from "../services/monitoring";

// Mock the monitoring service
vi.mock("../services/monitoring", () => ({
  monitoringService: {
    history: vi.fn(),
    containers: vi.fn(),
    vmInventory: vi.fn(),
  },
}));

// Mock the incidents service
vi.mock("../services/incidents", () => ({
  incidentsService: {
    list: vi.fn().mockResolvedValue({ incidents: [] }),
  },
}));

describe("InfrastructurePage - VM Section", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.clearAllMocks();

    // Default mocks for chart data
    vi.mocked(monitoringService.monitoringService.history).mockResolvedValue({
      metric: "cpu_utilization",
      unit: "percent",
      points: [],
      availability: "unavailable",
    });

    vi.mocked(monitoringService.monitoringService.containers).mockResolvedValue([]);
  });

  it("displays friendly static message indicating VM monitoring is not enabled", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <InfrastructurePage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Virtual machine monitoring is not currently enabled")).toBeTruthy();
    });

    expect(
      screen.getByText(
        "VM monitoring is planned for a future release. Your Docker containers and host infrastructure continue to be monitored normally."
      )
    ).toBeTruthy();
  });
});
