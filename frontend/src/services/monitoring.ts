import { apiRequest } from "./http";
import type { ContainerStatus, InfrastructureSummary, MetricHistory, VMInventoryResponse, VirtualMachineStatus } from "../types/monitoring";

export const monitoringService = {
  summary: () => apiRequest<InfrastructureSummary>("/infrastructure/summary"),
  history: (metric: string) => apiRequest<MetricHistory>(`/infrastructure/metrics/history?metric=${metric}&hours=6`),
  containers: () => apiRequest<ContainerStatus[]>("/infrastructure/containers"),
  containerDetails: (id: string) => apiRequest<Partial<ContainerStatus>>(`/infrastructure/containers/${encodeURIComponent(id)}/details`),
  vms: () => apiRequest<VirtualMachineStatus[]>("/infrastructure/vms"),
  vmInventory: () => apiRequest<VMInventoryResponse>("/infrastructure/vms/status"),
};
