import type { MetricReading } from "../types/monitoring";

const labels: Record<string, string> = { cpu_utilization: "CPU utilization", memory_utilization: "Memory utilization", disk_utilization: "Disk utilization", network_receive: "Network receive" };

export function MetricCard({ metric }: { metric: MetricReading | undefined }) {
  if (!metric || metric.availability !== "available" || metric.value === null) return <article className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5"><p className="text-sm text-zinc-400">{metric ? labels[metric.name] ?? metric.name : "Metric"}</p><p className="mt-5 text-xl font-medium text-amber-300">Unavailable</p><p className="mt-2 text-sm text-zinc-500">No current telemetry is available.</p></article>;
  const suffix = metric.unit === "percent" ? "%" : metric.unit === "bytes_per_second" ? " B/s" : "";
  return <article className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5"><p className="text-sm text-zinc-400">{labels[metric.name] ?? metric.name}</p><p className="mt-5 text-xl font-medium text-zinc-100">{metric.value.toFixed(metric.unit === "percent" ? 1 : 0)}{suffix}</p><p className="mt-2 text-sm text-zinc-500">Observed {new Date(metric.observation_at!).toLocaleTimeString()}</p></article>;
}
