import { AlertCircle, AlertTriangle, Info } from "lucide-react";
import type { IncidentSeverity } from "../types/incident";

const styles: Record<IncidentSeverity, string> = {
  INFO: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  WARNING: "border-amber-400/30 bg-amber-400/10 text-amber-200",
  HIGH: "border-orange-400/30 bg-orange-400/10 text-orange-300",
  CRITICAL: "border-red-400/30 bg-red-400/10 text-red-300",
};

export function SeverityBadge({ severity }: { severity: IncidentSeverity | string }) {
  const Icon = severity === "CRITICAL" ? AlertCircle : severity === "HIGH" || severity === "WARNING" ? AlertTriangle : Info;
  const className = styles[severity as IncidentSeverity] ?? "border-zinc-700 bg-zinc-800 text-zinc-300";
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${className}`}><Icon size={13} />{severity}</span>;
}
