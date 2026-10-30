import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { MetricCard } from "../components/metric-card";
import { monitoringService } from "../services/monitoring";

export function OverviewPage() {
  const summary = useQuery({ queryKey: ["infrastructure-summary"], queryFn: monitoringService.summary, refetchInterval: 30_000 });
  const data = summary.data;
  const state = data?.health.state ?? "UNKNOWN";
  const stateClass = state === "HEALTHY" ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-300" : state === "CRITICAL" ? "border-red-400/25 bg-red-400/10 text-red-300" : "border-amber-400/25 bg-amber-400/10 text-amber-300";
  return <section className="mx-auto max-w-6xl">
    <p className="text-sm font-medium text-cyan-300">Infrastructure overview</p>
    <div className="mt-2 flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-3xl font-semibold tracking-tight">Kibo status</h1><p className="mt-2 text-zinc-400">{data?.monitoring_available ? `Last collection: ${data.last_successful_collection ? new Date(data.last_successful_collection).toLocaleString() : "unknown"}` : "Monitoring is unavailable; health cannot be verified."}</p></div><div className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm ${stateClass}`}>{state === "HEALTHY" ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}{summary.isLoading ? "Loading telemetry" : state}</div></div>
    {summary.isError && <p className="mt-6 rounded-lg border border-amber-400/25 bg-amber-400/10 p-4 text-sm text-amber-200">Monitoring data could not be retrieved. KiboLens is not claiming the infrastructure is healthy.</p>}
    <div className="mt-8 grid gap-4 md:grid-cols-4"><MetricCard metric={data?.metrics.find((metric) => metric.name === "cpu_utilization")} /><MetricCard metric={data?.metrics.find((metric) => metric.name === "memory_utilization")} /><MetricCard metric={data?.metrics.find((metric) => metric.name === "disk_utilization")} /><MetricCard metric={data?.metrics.find((metric) => metric.name === "network_receive")} /></div>
    {data && <section className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5"><h2 className="font-medium">Assessment evidence</h2><ul className="mt-3 space-y-2 text-sm text-zinc-400">{data.health.evidence.map((item) => <li key={item}>{item}</li>)}</ul></section>}
  </section>;
}
