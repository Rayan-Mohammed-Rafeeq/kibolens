import { apiRequest } from "./http";
import type { ContainerStatus, InfrastructureSummary, MetricHistory } from "../types/monitoring";

export const monitoringService = {
  summary: () => apiRequest<InfrastructureSummary>("/infrastructure/summary"),
  history: (metric: string) => apiRequest<MetricHistory>(`/infrastructure/metrics/history?metric=${metric}&hours=6`),
  containers: () => apiRequest<ContainerStatus[]>("/infrastructure/containers"),
};
