import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Database } from "lucide-react";
import type { ReactNode } from "react";
import { getHealth } from "../services/api";

export function OverviewPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, refetchInterval: 30_000 });
  const available = health.isSuccess;
  return <section className="mx-auto max-w-6xl">
    <p className="text-sm font-medium text-cyan-300">Infrastructure overview</p>
    <div className="mt-2 flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-3xl font-semibold tracking-tight">Kibo status</h1><p className="mt-2 text-zinc-400">Live telemetry will appear here after monitoring is configured.</p></div><div className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm ${available ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-300" : "border-amber-400/25 bg-amber-400/10 text-amber-300"}`}>{available ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}{available ? "API reachable" : "API unavailable"}</div></div>
    <div className="mt-8 grid gap-4 md:grid-cols-3"><StatusCard title="API service" value={available ? health.data.service : "Unavailable"} detail={available ? `Checked ${new Date(health.data.timestamp).toLocaleTimeString()}` : "Start the backend to collect status."} /><StatusCard title="Database" value="Not yet configured" detail="No health claim is made until PostgreSQL is connected." icon={<Database size={18} />} /><StatusCard title="Live telemetry" value="Not configured" detail="Prometheus integration begins in Phase 3." /></div>
  </section>;
}

function StatusCard({ title, value, detail, icon }: { title: string; value: string; detail: string; icon?: ReactNode }) {
  return <article className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5"><div className="flex items-center justify-between text-sm text-zinc-400"><span>{title}</span>{icon}</div><p className="mt-5 text-xl font-medium text-zinc-100">{value}</p><p className="mt-2 text-sm leading-6 text-zinc-500">{detail}</p></article>;
}
