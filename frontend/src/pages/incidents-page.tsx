import { useQuery } from "@tanstack/react-query";
import { AlertCircle, AlertTriangle, ChevronLeft, ChevronRight, Info, Search } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { incidentsService } from "../services/incidents";
import type { IncidentSeverity, IncidentStatus } from "../types/incident";
import { formatTimestamp, getRelativeTime, getSeverityColor, getStatusColor } from "../utils/incident";

export function IncidentsPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [severityFilter, setSeverityFilter] = useState<IncidentSeverity | "">("");
  const [statusFilter, setStatusFilter] = useState<IncidentStatus | "">("");
  
  const pageSize = 20;

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["incidents", page, search, severityFilter, statusFilter],
    queryFn: () =>
      incidentsService.list({
        page,
        page_size: pageSize,
        search: search || undefined,
        severity: severityFilter || undefined,
        status: statusFilter || undefined,
      }),
    refetchInterval: 30_000,
  });

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0;

  return (
    <section className="page-shell">
      <div className="flex items-end justify-between">
        <div>
          <p className="page-eyebrow">Incident management</p>
          <h1 className="page-title">Incidents</h1>
          <p className="mt-2 text-zinc-400">
            {data ? `${data.total} total incident${data.total !== 1 ? "s" : ""}` : "Loading incidents..."}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="panel mt-8 flex flex-wrap gap-3 p-4">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={16} />
          <input
            type="text"
            placeholder="Search incidents..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="field-control w-full py-2 pl-10 pr-4 text-sm"
          />
        </div>

        <select
          value={severityFilter}
          onChange={(e) => {
            setSeverityFilter(e.target.value as IncidentSeverity | "");
            setPage(1);
          }}
          className="field-control px-4 py-2 text-sm"
        >
          <option value="">All severities</option>
          <option value="CRITICAL">Critical</option>
          <option value="HIGH">High</option>
          <option value="WARNING">Warning</option>
          <option value="INFO">Info</option>
        </select>

        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value as IncidentStatus | "");
            setPage(1);
          }}
          className="field-control px-4 py-2 text-sm"
        >
          <option value="">All statuses</option>
          <option value="DETECTED">Detected</option>
          <option value="INVESTIGATING">Investigating</option>
          <option value="IDENTIFIED">Identified</option>
          <option value="RESOLVING">Resolving</option>
          <option value="RESOLVED">Resolved</option>
          <option value="CLOSED">Closed</option>
        </select>
      </div>

      {/* Error state */}
      {isError && (
        <div className="mt-6 rounded-lg border border-red-400/25 bg-red-400/10 p-4 flex items-start gap-3">
          <AlertCircle className="text-red-300 flex-shrink-0 mt-0.5" size={20} />
          <div>
            <p className="font-medium text-red-200">Could not load incidents</p>
            <p className="mt-1 text-sm text-red-300">{error instanceof Error ? error.message : "An error occurred"}</p>
          </div>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900/40 p-8 text-center text-zinc-400">
          Loading incidents...
        </div>
      )}

      {/* Empty state */}
      {data && data.incidents.length === 0 && !isLoading && (
        <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900/40 p-8 text-center">
          <Info className="mx-auto text-zinc-600" size={32} />
          <p className="mt-3 font-medium text-zinc-300">No incidents found</p>
          <p className="mt-1 text-sm text-zinc-500">
            {search || severityFilter || statusFilter
              ? "Try adjusting your filters"
              : "No incidents have been detected yet"}
          </p>
        </div>
      )}

      {/* Incidents table */}
      {data && data.incidents.length > 0 && (
        <>
          <div className="panel mt-6 overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3 font-medium">Reference</th>
                  <th className="px-4 py-3 font-medium">Title</th>
                  <th className="px-4 py-3 font-medium">Severity</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Affected Service</th>
                  <th className="px-4 py-3 font-medium">Updated</th>
                </tr>
              </thead>
              <tbody>
                {data.incidents.map((incident) => (
                  <tr
                    key={incident.id}
                    className="border-b border-slate-800/70 last:border-0 transition-colors hover:bg-cyan-400/[.04]"
                  >
                    <td className="px-4 py-3">
                      <Link
                        to={`/incidents/${incident.id}`}
                        className="font-mono text-sm text-cyan-400 hover:text-cyan-300"
                      >
                        {incident.incident_number}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        to={`/incidents/${incident.id}`}
                        className="text-sm hover:text-white transition-colors"
                      >
                        {incident.title}
                      </Link>
                      {incident.description && (
                        <p className="mt-0.5 text-xs text-zinc-500 line-clamp-1">
                          {incident.description}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${getSeverityColor(incident.severity)}`}
                      >
                        {incident.severity === "CRITICAL" ? (
                          <AlertCircle size={12} />
                        ) : incident.severity === "HIGH" || incident.severity === "WARNING" ? (
                          <AlertTriangle size={12} />
                        ) : (
                          <Info size={12} />
                        )}
                        {incident.severity}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${getStatusColor(incident.status)}`}
                      >
                        {incident.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-zinc-400">
                      {incident.source === "simulation" && <span className="mr-2 rounded bg-fuchsia-400/15 px-2 py-0.5 text-xs text-fuchsia-200">SIMULATED</span>}
                      {incident.affected_service || (
                        <span className="text-zinc-600">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-zinc-400" title={formatTimestamp(incident.updated_at)}>
                        {getRelativeTime(incident.updated_at)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-between text-sm">
              <p className="text-zinc-500">
                Page {page} of {totalPages}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-1.5 hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ChevronLeft size={16} />
                  Previous
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-1.5 hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Next
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
