export type HealthState = "HEALTHY" | "DEGRADED" | "CRITICAL" | "UNKNOWN";
export type Availability = "available" | "stale" | "unavailable";

export interface MetricReading { name: string; value: number | null; unit: string; observation_at: string | null; availability: Availability; }
export interface InfrastructureSummary { health: { state: HealthState; evidence: string[]; assessed_at: string }; metrics: MetricReading[]; monitoring_available: boolean; last_successful_collection: string | null; }
export interface MetricHistory { metric: string; unit: string; points: Array<{ timestamp: string; value: number }>; availability: Availability; }
export interface ContainerStatus { id: string | null; name: string; status: "RUNNING" | "STOPPED" | "UNHEALTHY" | "UNKNOWN"; cpu_percent: number | null; memory_bytes: number | null; network_receive_bytes_per_second: number | null; network_transmit_bytes_per_second: number | null; restart_count?: number | null; last_observation: string | null; availability: Availability; image?: string | null; exit_code?: number | null; labels?: Record<string, string>; logs?: string | null; }
