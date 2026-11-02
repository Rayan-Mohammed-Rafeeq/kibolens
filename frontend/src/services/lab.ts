import { apiRequest } from "./http";

export const labScenarios = ["crasher", "unhealthy", "restart-loop", "cpu-stress", "memory-pressure", "missing-dependency", "config-error"] as const;
export type LabScenario = typeof labScenarios[number];
export interface LabContainer { id?: string; name: string; status: string; labels?: Record<string, string>; exit_code?: number | null; logs?: string; }
export const labService = {
  status: () => apiRequest<LabContainer[]>("/infrastructure/lab"),
  start: (scenario: LabScenario) => apiRequest<{ name: string; status: string }>(`/infrastructure/lab/${scenario}/start`, { method: "POST", body: "{}" }),
  stop: (scenario: LabScenario) => apiRequest<{ stopped: boolean }>(`/infrastructure/lab/${scenario}/stop`, { method: "POST", body: "{}" }),
  reset: () => apiRequest<{ removed_containers: number; closed_incidents: number }>("/infrastructure/lab/reset", { method: "POST", body: "{}" }),
};
