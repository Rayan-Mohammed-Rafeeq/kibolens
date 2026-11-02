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

describe("InfrastructurePage - VM Empty State", () => {
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

  it("displays empty state for unconfigured VM integration (socket absent)", async () => {
    vi.mocked(monitoringService.monitoringService.vmInventory).mockResolvedValue({
      items: [],
      availability: "available",
      detail: null,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <InfrastructurePage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("No virtual machines detected")).toBeTruthy();
    });

    expect(
      screen.getByText(
        /No libvirt-managed virtual machines are currently configured on this host/i
      )
    ).toBeTruthy();

    expect(
      screen.getByText(/Configure libvirt on this host to monitor virtual machines/i)
    ).toBeTruthy();
  });

  it("displays empty state when libvirt connects successfully with zero VMs", async () => {
    vi.mocked(monitoringService.monitoringService.vmInventory).mockResolvedValue({
      items: [],
      availability: "available",
      detail: null,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <InfrastructurePage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      const heading = screen.getAllByText("No virtual machines detected")[0];
      expect(heading).toBeTruthy();
    });
  });

  it("displays error state when libvirt socket exists but connection fails", async () => {
    vi.mocked(monitoringService.monitoringService.vmInventory).mockResolvedValue({
      items: [],
      availability: "unavailable",
      detail:
        "VM inventory is unavailable: the libvirt connection 'qemu:///system' could not be queried. Permission denied",
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <InfrastructurePage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(
        screen.getByText(/VM inventory is unavailable.*Permission denied/i)
      ).toBeTruthy();
    });
  });

  it("displays error state when libvirt daemon is configured but unavailable", async () => {
    vi.mocked(monitoringService.monitoringService.vmInventory).mockResolvedValue({
      items: [],
      availability: "unavailable",
      detail:
        "VM inventory is unavailable: the libvirt connection 'qemu:///system' could not be queried. failed to connect to the libvirt daemon",
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <InfrastructurePage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(
        screen.getByText(/VM inventory is unavailable.*failed to connect/i)
      ).toBeTruthy();
    });
  });

  it("displays VM inventory when VMs are discovered", async () => {
    vi.mocked(monitoringService.monitoringService.vmInventory).mockResolvedValue({
      items: [
        {
          id: "vm-1",
          name: "test-vm",
          status: "RUNNING",
          vcpu_count: 2,
          memory_allocated_bytes: 2147483648,
          memory_used_bytes: 1073741824,
          cpu_percent: 25.5,
          disk_read_bytes: null,
          disk_write_bytes: null,
          network_receive_bytes: null,
          network_transmit_bytes: null,
          ip_addresses: ["192.168.122.10"],
          operating_system: "hvm",
          guest_agent_configured: true,
          uptime_seconds: 3600,
          last_observation: new Date().toISOString(),
          availability: "available",
          error: null,
        },
      ],
      availability: "available",
      detail: null,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <InfrastructurePage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("test-vm")).toBeTruthy();
    });

    expect(screen.getByText(/192.168.122.10/)).toBeTruthy();
    expect(screen.getByText("RUNNING")).toBeTruthy();
  });

  it("displays generic error when API request fails completely", async () => {
    vi.mocked(monitoringService.monitoringService.vmInventory).mockRejectedValue(
      new Error("Network error")
    );

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <InfrastructurePage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          /VM inventory is unavailable because the host libvirt connection could not be queried/i
        )
      ).toBeTruthy();
    });
  });
});
