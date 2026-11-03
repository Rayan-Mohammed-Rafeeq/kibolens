import { apiRequest } from "./http";

export const labScenarios = ["interview-demo", "high-cpu", "high-memory", "critical-memory", "high-temperature", "disk-nearly-full", "container-crash", "container-restart-loop", "container-unhealthy", "application-config-failure", "vm-unavailable", "vm-memory-exhaustion", "vm-disk-nearly-full", "network-connectivity-failure"] as const;
export type LabScenario = typeof labScenarios[number];
export interface LabContainer { id?: string; name: string; status: string; labels?: Record<string, string>; exit_code?: number | null; logs?: string; incident_id?: string; notification?: { requested: boolean; status: string; detail?: string }; }
export const labService = {
  status: () => apiRequest<LabContainer[]>("/infrastructure/lab"),
  scenarios: () => apiRequest<Array<{ key: string; title: string; severity: string; resource: string; description: string; safe_synthetic: boolean }>>("/infrastructure/lab/scenarios"),
  start: (scenario: LabScenario, physical = false, notify_account = false, healthy = false) => apiRequest<{ name: string; status: string; simulated?: boolean; incident_id?: string; notification?: { requested: boolean; status: string; detail?: string } }>(`/infrastructure/lab/${scenario}/start`, { method: "POST", body: JSON.stringify({ physical, notify_account, healthy }) }),
  recover: () => apiRequest<{ name: string; status: string }>("/infrastructure/lab/interview-demo/recover", { method: "POST", body: "{}" }),
  stop: (scenario: LabScenario) => apiRequest<{ stopped: boolean }>(`/infrastructure/lab/${scenario}/stop`, { method: "POST", body: "{}" }),
  reset: () => apiRequest<{ removed_containers: number; closed_incidents: number }>("/infrastructure/lab/reset", { method: "POST", body: "{}" }),
};
