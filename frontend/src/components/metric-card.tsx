import type { MetricReading } from "../types/monitoring";

const labels: Record<string, string> = { cpu_utilization: "CPU utilization", memory_utilization: "Memory utilization", disk_utilization: "Disk utilization", network_receive: "Network receive" };

export function MetricCard({ metric }: { metric: MetricReading | undefined }) {
  if (!metric || metric.availability !== "available" || metric.value === null) return <article className="panel panel-hover min-h-[140px] p-5"><div className="flex items-center justify-between"><p className="section-kicker">{metric ? labels[metric.name] ?? metric.name : "Metric"}</p><span className="h-2 w-2 rounded-full bg-amber-300" /></div><p className="mt-6 text-xl font-semibold text-amber-200">Unavailable</p><p className="mt-1 text-sm text-slate-500">No current telemetry is available.</p></article>;
  const suffix = metric.unit === "percent" ? "%" : metric.unit === "bytes_per_second" ? " B/s" : "";
  return <article className="panel panel-hover min-h-[140px] p-5"><div className="flex items-center justify-between"><p className="section-kicker">{labels[metric.name] ?? metric.name}</p><span className="h-2 w-2 rounded-full bg-emerald-300 shadow-[0_0_12px_rgba(110,231,183,.7)]" /></div><p className="mt-5 text-3xl font-semibold tracking-tight text-slate-100">{metric.value.toFixed(metric.unit === "percent" ? 1 : 0)}<span className="ml-1 text-base font-medium text-cyan-300">{suffix}</span></p><p className="mt-1 text-xs text-slate-500">Observed {new Date(metric.observation_at!).toLocaleTimeString()}</p></article>;
}
