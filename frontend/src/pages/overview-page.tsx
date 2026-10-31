import { useQuery } from "@tanstack/react-query";
import { AlertCircle, AlertTriangle, CheckCircle2, Siren } from "lucide-react";
import { Link } from "react-router-dom";
import { MetricCard } from "../components/metric-card";
import { monitoringService } from "../services/monitoring";
import { incidentsService } from "../services/incidents";
import { getSeverityColor, getStatusColor, getRelativeTime } from "../utils/incident";

export function OverviewPage() {
  const summary = useQuery({ queryKey: ["infrastructure-summary"], queryFn: monitoringService.summary, refetchInterval: 30_000 });
  const incidentSummary = useQuery({ queryKey: ["incident-summary"], queryFn: incidentsService.summary, refetchInterval: 30_000 });
  
  const data = summary.data;
  const incidents = incidentSummary.data;
  const state = data?.health.state ?? "UNKNOWN";
  const stateClass = state === "HEALTHY" ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-300" : state === "CRITICAL" ? "border-red-400/25 bg-red-400/10 text-red-300" : "border-amber-400/25 bg-amber-400/10 text-amber-300";
  
  return <section className="mx-auto max-w-6xl">
    <p className="text-sm font-medium text-cyan-300">Infrastructure overview</p>
    <div className="mt-2 flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-3xl font-semibold tracking-tight">Kibo status</h1><p className="mt-2 text-zinc-400">{data?.monitoring_available ? `Last collection: ${data.last_successful_collection ? new Date(data.last_successful_collection).toLocaleString() : "unknown"}` : "Monitoring is unavailable; health cannot be verified."}</p></div><div className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm ${stateClass}`}>{state === "HEALTHY" ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}{summary.isLoading ? "Loading telemetry" : state}</div></div>
    {summary.isError && <p className="mt-6 rounded-lg border border-amber-400/25 bg-amber-400/10 p-4 text-sm text-amber-200">Monitoring data could not be retrieved. KiboLens is not claiming the infrastructure is healthy.</p>}
    
    {/* Incidents Summary */}
    {incidents && (
      <div className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Active Incidents</h2>
          <Link to="/incidents" className="text-sm text-cyan-400 hover:text-cyan-300">View all →</Link>
        </div>
        <div className="mt-4 grid gap-3 grid-cols-2 md:grid-cols-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/80 p-3">
            <div className="flex items-center gap-2">
              <Siren size={14} className="text-zinc-500" />
              <span className="text-xs text-zinc-400">Total Active</span>
            </div>
            <p className="mt-2 text-2xl font-semibold">{incidents.total_active}</p>
          </div>
          <div className="rounded-lg border border-red-400/25 bg-red-400/5 p-3">
            <div className="flex items-center gap-2">
              <AlertCircle size={14} className="text-red-400" />
              <span className="text-xs text-red-300">Critical</span>
            </div>
            <p className="mt-2 text-2xl font-semibold text-red-300">{incidents.critical_count}</p>
          </div>
          <div className="rounded-lg border border-orange-400/25 bg-orange-400/5 p-3">
            <div className="flex items-center gap-2">
              <AlertTriangle size={14} className="text-orange-400" />
              <span className="text-xs text-orange-300">High</span>
            </div>
            <p className="mt-2 text-2xl font-semibold text-orange-300">{incidents.high_count}</p>
          </div>
          <div className="rounded-lg border border-yellow-400/25 bg-yellow-400/5 p-3">
            <div className="flex items-center gap-2">
              <AlertTriangle size={14} className="text-yellow-400" />
              <span className="text-xs text-yellow-300">Warning</span>
            </div>
            <p className="mt-2 text-2xl font-semibold text-yellow-300">{incidents.warning_count}</p>
          </div>
        </div>
        {incidents.latest_incidents.length > 0 && (
          <div className="mt-4 border-t border-zinc-800 pt-4">
            <p className="text-sm text-zinc-400 mb-3">Latest incidents</p>
            <div className="space-y-2">
              {incidents.latest_incidents.slice(0, 3).map((incident) => (
                <Link
                  key={incident.id}
                  to={`/incidents/${incident.id}`}
                  className="block rounded-lg border border-zinc-800 bg-zinc-900/80 p-3 hover:bg-zinc-800/80 transition-colors"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-zinc-300 truncate">{incident.title}</p>
                      <div className="mt-1 flex items-center gap-2">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${getSeverityColor(incident.severity)}`}>
                          {incident.severity}
                        </span>
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${getStatusColor(incident.status)}`}>
                          {incident.status}
                        </span>
                      </div>
                    </div>
                    <span className="text-xs text-zinc-500 whitespace-nowrap">{getRelativeTime(incident.updated_at)}</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    )}
    
    <div className="mt-8 grid gap-4 md:grid-cols-4"><MetricCard metric={data?.metrics.find((metric) => metric.name === "cpu_utilization")} /><MetricCard metric={data?.metrics.find((metric) => metric.name === "memory_utilization")} /><MetricCard metric={data?.metrics.find((metric) => metric.name === "disk_utilization")} /><MetricCard metric={data?.metrics.find((metric) => metric.name === "network_receive")} /></div>
    {data && <section className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5"><h2 className="font-medium">Assessment evidence</h2><ul className="mt-3 space-y-2 text-sm text-zinc-400">{data.health.evidence.map((item) => <li key={item}>{item}</li>)}</ul></section>}
  </section>;
}
