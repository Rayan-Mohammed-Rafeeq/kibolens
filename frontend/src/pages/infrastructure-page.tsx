import { useQuery } from "@tanstack/react-query";
import { Activity, ChevronDown, ChevronLeft, ChevronRight, Server } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { MarkdownRenderer } from "../components/markdown-renderer";
import { incidentsService } from "../services/incidents";
import { monitoringService } from "../services/monitoring";
import type { ContainerStatus, MetricHistory } from "../types/monitoring";

export function InfrastructurePage() {
  const cpu = useQuery({ queryKey: ["metric-history", "cpu"], queryFn: () => monitoringService.history("cpu_utilization"), refetchInterval: 60_000 });
  const memory = useQuery({ queryKey: ["metric-history", "memory"], queryFn: () => monitoringService.history("memory_utilization"), refetchInterval: 60_000 });
  const containers = useQuery({ queryKey: ["containers"], queryFn: monitoringService.containers, refetchInterval: 30_000, staleTime: 10_000, refetchIntervalInBackground: false });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const totalContainers = containers.data?.length ?? 0;
  const pageCount = Math.max(1, Math.ceil(totalContainers / pageSize));
  const pageItems = containers.data?.slice((page - 1) * pageSize, page * pageSize) ?? [];
  useEffect(() => { if (page > pageCount) setPage(pageCount); }, [page, pageCount]);
  const selected = containers.data?.find((container) => container.id === selectedId);
  const selectedDetails = useQuery({
    queryKey: ["container-details", selected?.id],
    queryFn: () => monitoringService.containerDetails(selected!.id!),
    enabled: Boolean(selected),
  });

  const relatedIncidents = useQuery({
    queryKey: ["container-incidents", selected?.id, selected?.compose_service, selected?.name],
    queryFn: () => incidentsService.list({ affected_service: selected?.compose_service ?? selected?.name }),
    enabled: Boolean(selected),
  });

  return <section className="mx-auto max-w-6xl">
    <p className="text-sm font-medium text-cyan-300">Infrastructure</p>
    <h1 className="mt-2 text-3xl font-semibold tracking-tight">Telemetry, containers and virtual machines</h1>
    <p className="mt-2 text-zinc-400">One canonical container record per Docker ID, merged from Docker, Compose, cAdvisor and Prometheus. Docker health and telemetry availability are reported separately.</p>

    <div className="mt-8 grid gap-4 lg:grid-cols-2">
      <HistoryChart title="CPU utilization" history={cpu.data} loading={cpu.isLoading} />
      <HistoryChart title="Memory utilization" history={memory.data} loading={memory.isLoading} />
    </div>

    <section className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/40">
      <header className="flex flex-wrap items-center gap-2 border-b border-zinc-800 px-5 py-4"><Server size={17} className="text-cyan-300" /><h2 className="font-medium">Container inventory</h2><span className="ml-auto text-xs text-zinc-500">{containers.isLoading ? "Loading inventory…" : `${totalContainers} Docker container(s)`}</span></header>
      {containers.isLoading && !containers.data ? <div className="space-y-3 p-5"><InventorySkeleton /><InventorySkeleton /><InventorySkeleton /></div> : containers.isError ? <div className="p-5"><p className="text-sm text-red-300">Docker inventory could not be loaded.</p><p className="mt-1 text-xs text-zinc-500">{(containers.error as Error).message}</p></div> : totalContainers ? <><div className="divide-y divide-zinc-800">{pageItems.map((container) => <ContainerRow key={container.id ?? container.name} container={container} selected={container.id === selectedId} onSelect={() => setSelectedId(container.id === selectedId ? null : container.id)} />)}</div><div className="flex items-center justify-between border-t border-zinc-800 px-5 py-3 text-xs text-zinc-500"><span>Page {page} of {pageCount}</span><div className="flex gap-2"><button type="button" aria-label="Previous container page" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page === 1} className="rounded border border-zinc-700 p-1.5 hover:border-cyan-400 disabled:opacity-30"><ChevronLeft size={15} /></button><button type="button" aria-label="Next container page" onClick={() => setPage((current) => Math.min(pageCount, current + 1))} disabled={page === pageCount} className="rounded border border-zinc-700 p-1.5 hover:border-cyan-400 disabled:opacity-30"><ChevronRight size={15} /></button></div></div></> : <p className="p-5 text-sm text-zinc-500">No containers found. Docker may be unavailable or no containers are currently running.</p>}
      {containers.isFetching && !containers.isLoading && <p className="border-t border-zinc-800 px-5 py-2 text-xs text-cyan-300">Refreshing inventory in the background…</p>}
    </section>

     {selected && <ContainerDetails container={{ ...selected, ...(selectedDetails.data ?? {}) }} incidents={relatedIncidents.data?.incidents ?? []} incidentsLoading={relatedIncidents.isLoading} />}

    <section className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/40">
      <header className="flex items-center gap-2 border-b border-zinc-800 px-5 py-4"><Server size={17} className="text-cyan-300" /><h2 className="font-medium">Virtual machines</h2></header>
      <div className="p-5">
        <p className="text-sm font-medium text-zinc-300">Virtual machine monitoring is not currently enabled</p>
        <p className="mt-1 text-sm text-zinc-500">VM monitoring is planned for a future release. Your Docker containers and host infrastructure continue to be monitored normally.</p>
      </div>
    </section>
  </section>;
}

function ContainerRow({ container, selected, onSelect }: { container: ContainerStatus; selected: boolean; onSelect: () => void }) {
  return <button type="button" onClick={onSelect} className="block w-full p-5 text-left transition-colors hover:bg-zinc-800/50">
    <div className="flex items-start justify-between gap-4">
      <div className="flex min-w-0 items-start gap-3">
        <span className="mt-1 text-zinc-500">{selected ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</span>
        <div className="min-w-0">
          <p className="truncate font-medium text-zinc-100">{container.name}</p>
          <p className="mt-1 truncate text-xs text-zinc-500">{container.compose_service ?? "Compose service not reported"} · {container.image ?? "Image not reported"}</p>
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap justify-end gap-2 text-xs">
        <Badge label={container.docker_state} tone={container.docker_state === "RUNNING" ? "green" : "amber"} />
        <Badge label={container.health === "NO_CHECK" ? "NO HEALTHCHECK" : container.health} tone={container.health === "HEALTHY" ? "green" : container.health === "UNHEALTHY" ? "red" : "amber"} />
      </div>
    </div>
     <div className="mt-3 grid gap-2 text-sm text-zinc-400 sm:grid-cols-2 lg:grid-cols-4">
      <span>CPU {display(container.cpu_percent, "%")}</span><span>Memory {displayBytes(container.memory_bytes)}{container.memory_limit_bytes ? ` / ${displayBytes(container.memory_limit_bytes)}` : ""}</span><span>RX {displayBytes(container.network_receive_bytes_per_second)}/s</span><span>TX {displayBytes(container.network_transmit_bytes_per_second)}/s</span>
    </div>
     <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500"><span>Telemetry: {container.availability === "unavailable" ? "unavailable" : container.availability}</span><span>Restarts: {container.restart_count ?? "—"}</span><span>Uptime: {formatUptime(container.uptime_seconds)}</span>{container.exit_code !== null && container.exit_code !== undefined && <span>Exit: {container.exit_code}</span>}</div>
    {container.error && <p className="mt-2 truncate text-xs text-red-300">{container.error}</p>}
  </button>;
}

function ContainerDetails({ container, incidents, incidentsLoading }: { container: ContainerStatus; incidents: Array<{ id: string; incident_number: string; title: string; status: string }>; incidentsLoading: boolean }) {
  return <section className="mt-4 rounded-xl border border-cyan-400/20 bg-zinc-900/40 p-5"><div className="flex items-center justify-between gap-4"><div><p className="text-xs font-medium uppercase tracking-wide text-cyan-300">Container details</p><h2 className="mt-1 text-lg font-semibold">{container.name}</h2></div><span className="font-mono text-xs text-zinc-500">{container.id ?? "ID unavailable"}</span></div><div className="mt-4 grid gap-3 text-sm text-zinc-300 sm:grid-cols-2 lg:grid-cols-4"><Detail label="Docker state" value={container.docker_state} /><Detail label="Health" value={container.health === "NO_CHECK" ? "No Docker healthcheck" : container.health} /><Detail label="CPU" value={display(container.cpu_percent, "%")} /><Detail label="Memory" value={displayBytes(container.memory_bytes)} /><Detail label="Network RX" value={`${displayBytes(container.network_receive_bytes_per_second)}/s`} /><Detail label="Network TX" value={`${displayBytes(container.network_transmit_bytes_per_second)}/s`} /><Detail label="Restarts" value={`${container.restart_count ?? "—"}`} /><Detail label="Uptime" value={formatUptime(container.uptime_seconds)} /></div><div className="mt-5 grid gap-5 lg:grid-cols-2"><div><h3 className="font-medium text-zinc-200">Docker logs</h3>{container.logs ? <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-zinc-950 p-3 text-xs text-zinc-400">{container.logs}</pre> : <p className="mt-2 text-sm text-zinc-500">No Docker logs are available.</p>}</div><div><h3 className="font-medium text-zinc-200">Related incidents</h3>{incidentsLoading ? <p className="mt-2 text-sm text-zinc-500">Loading incidents…</p> : incidents.length ? <ul className="mt-2 space-y-2">{incidents.map((incident) => <li key={incident.id}><Link className="text-sm text-cyan-300 hover:text-cyan-200" to={`/incidents/${incident.id}`}>{incident.incident_number} · {incident.title} · {incident.status}</Link></li>)}</ul> : <p className="mt-2 text-sm text-zinc-500">No incidents are associated with this service.</p>}</div></div><div className="mt-5"><h3 className="font-medium text-zinc-200">Telemetry evidence</h3><p className="mt-2 text-sm text-zinc-400">Telemetry status: <span className="text-zinc-200">{container.availability}</span>. Values marked — were not reported by Docker or cAdvisor.</p>{container.error && <MarkdownRenderer content={`**Docker error:** ${container.error}`} />}</div></section>;
}

function Detail({ label, value }: { label: string; value: string }) { return <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3"><p className="text-xs text-zinc-500">{label}</p><p className="mt-1">{value}</p></div>; }
function Badge({ label, tone }: { label: string; tone: "green" | "amber" | "red" }) { const colors = { green: "border-emerald-400/25 bg-emerald-400/10 text-emerald-300", amber: "border-amber-400/25 bg-amber-400/10 text-amber-200", red: "border-red-400/25 bg-red-400/10 text-red-300" }; return <span className={`rounded-full border px-2.5 py-1 ${colors[tone]}`}>{label}</span>; }
function display(value: number | null, suffix = ""): string { return value === null ? "—" : `${value.toFixed(1)}${suffix}`; }
function displayBytes(value: number | null): string { return value === null ? "—" : value > 1_048_576 ? `${(value / 1_048_576).toFixed(1)} MiB` : `${value.toFixed(0)} B`; }
function formatUptime(value?: number | null): string { if (value === null || value === undefined) return "—"; const hours = Math.floor(value / 3600); const minutes = Math.floor((value % 3600) / 60); return hours ? `${hours}h ${minutes}m` : `${minutes}m`; }
function HistoryChart({ title, history, loading }: { title: string; history?: MetricHistory; loading: boolean }) { const data = history?.points.map((point) => ({ ...point, label: new Date(point.timestamp).toLocaleTimeString() })) ?? []; return <article className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5"><div className="flex items-center gap-2"><Activity size={17} className="text-cyan-300" /><h2 className="font-medium">{title}</h2></div>{loading ? <p className="grid h-56 place-items-center text-sm text-zinc-500">Loading historical telemetry…</p> : history?.availability === "available" && data.length ? <div className="mt-5 h-56"><ResponsiveContainer width="100%" height="100%"><LineChart data={data}><XAxis dataKey="label" hide /><YAxis width={32} /><Tooltip /><Line dataKey="value" stroke="#22d3ee" dot={false} strokeWidth={2} /></LineChart></ResponsiveContainer></div> : <p className="grid h-56 place-items-center text-center text-sm text-zinc-500">Historical telemetry is unavailable. No chart data is fabricated.</p>}</article>; }
function InventorySkeleton() { return <div className="h-24 animate-pulse rounded-lg bg-zinc-800/60" />; }
