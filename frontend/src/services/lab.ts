import { apiRequest } from "./http";

export const labScenarios = ["high-cpu", "high-memory", "critical-memory", "high-temperature", "disk-nearly-full", "container-crash", "container-restart-loop", "container-unhealthy", "application-config-failure"] as const;
export type LabScenario = typeof labScenarios[number];
export interface LabDelivery { recipient: string; status: string; provider_id?: string | null; detail?: string | null; attempts?: number; }
export interface LabEvidence { type: string; metric_name?: string | null; value?: number | null; unit?: string | null; observed_at?: string | null; metadata?: Record<string, unknown>; }
export interface LabContainer { id?: string; name: string; status: string; labels?: Record<string, string>; exit_code?: number | null; logs?: string; incident_id?: string; evidence?: LabEvidence[]; notification?: { requested: boolean; status: string; detail?: string | null; deliveries?: LabDelivery[] }; }
export const labService = {
  status: () => apiRequest<LabContainer[]>("/infrastructure/lab"),
  scenarios: () => apiRequest<Array<{ key: string; title: string; severity: string; resource: string; description: string; safe_synthetic: boolean }>>("/infrastructure/lab/scenarios"),
  start: (scenario: LabScenario, physical = false, healthy = false) => apiRequest<{ name: string; status: string; simulated?: boolean; incident_id?: string; notification?: { requested: boolean; status: string; detail?: string; delivery_results?: LabDelivery[] } }>(`/infrastructure/lab/${scenario}/start`, { method: "POST", body: JSON.stringify({ physical, notify_account: true, healthy }) }),
  stop: (scenario: LabScenario) => apiRequest<{ stopped: boolean }>(`/infrastructure/lab/${scenario}/stop`, { method: "POST", body: "{}" }),
  reset: () => apiRequest<{ removed_containers: number; closed_incidents: number }>("/infrastructure/lab/reset", { method: "POST", body: "{}" }),
};
