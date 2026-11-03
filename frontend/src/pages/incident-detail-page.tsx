import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowLeft, Clock, Server } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { incidentsService } from "../services/incidents";
import { SeverityBadge } from "../components/severity-badge";
import type { IncidentSeverity, IncidentStatus } from "../types/incident";
import { formatTimestamp, getStatusColor } from "../utils/incident";

const VALID_TRANSITIONS: Record<IncidentStatus, IncidentStatus[]> = {
  DETECTED: ["INVESTIGATING", "RESOLVED"],
  INVESTIGATING: ["IDENTIFIED", "DETECTED", "RESOLVED"],
  IDENTIFIED: ["RESOLVING", "INVESTIGATING", "RESOLVED"],
  RESOLVING: ["RESOLVED", "IDENTIFIED"],
  RESOLVED: ["CLOSED", "INVESTIGATING"],
  CLOSED: [],
};

export function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [note, setNote] = useState("");
  const [newStatus, setNewStatus] = useState<IncidentStatus | "">("");
  const [newSeverity, setNewSeverity] = useState<IncidentSeverity | "">("");
  const [investigationQuestion, setInvestigationQuestion] = useState("What caused this incident and how should recovery be verified?");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["incident", id],
    queryFn: () => incidentsService.get(id!),
    enabled: !!id,
    refetchInterval: 15_000,
  });

  const updateStatusMutation = useMutation({
    mutationFn: ({ status, note }: { status: IncidentStatus; note?: string }) =>
      incidentsService.updateStatus(id!, status, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incident", id] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      queryClient.invalidateQueries({ queryKey: ["incident-summary"] });
      setNewStatus("");
      setNote("");
    },
  });

  const updateSeverityMutation = useMutation({
    mutationFn: ({ severity, note }: { severity: IncidentSeverity; note?: string }) =>
      incidentsService.updateSeverity(id!, severity, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incident", id] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      queryClient.invalidateQueries({ queryKey: ["incident-summary"] });
      setNewSeverity("");
      setNote("");
    },
  });

  const addNoteMutation = useMutation({
    mutationFn: (note: string) => incidentsService.addNote(id!, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incident", id] });
      setNote("");
    },
  });
  const investigateMutation = useMutation({
    mutationFn: () => incidentsService.investigate(id!, investigationQuestion),
    onSuccess: (result) => navigate(`/chat?conversation=${result.conversation_id}`),
  });

  if (isLoading) {
    return (
      <section className="mx-auto max-w-5xl">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-8 text-center text-zinc-400">
          Loading incident details...
        </div>
      </section>
    );
  }

  if (isError || !data) {
    return (
      <section className="mx-auto max-w-5xl">
        <Link to="/incidents" className="inline-flex items-center gap-2 text-sm text-zinc-400 hover:text-white">
          <ArrowLeft size={16} />
          Back to incidents
        </Link>
        <div className="mt-6 rounded-lg border border-red-400/25 bg-red-400/10 p-6 flex items-start gap-3">
          <AlertCircle className="text-red-300 flex-shrink-0 mt-0.5" size={20} />
          <div>
            <p className="font-medium text-red-200">Could not load incident</p>
            <p className="mt-1 text-sm text-red-300">
              {error instanceof Error ? error.message : "An error occurred"}
            </p>
          </div>
        </div>
      </section>
    );
  }

  const { incident, events, evidence } = data;
  const validNextStatuses = VALID_TRANSITIONS[incident.status as IncidentStatus] || [];

  return (
    <section className="mx-auto max-w-5xl">
      {/* Header */}
      <Link to="/incidents" className="inline-flex items-center gap-2 text-sm text-zinc-400 hover:text-white">
        <ArrowLeft size={16} />
        Back to incidents
      </Link>

      <div className="mt-4 flex items-start justify-between gap-4">
        <div>
            <p className="font-mono text-sm text-cyan-400">{incident.incident_number} {incident.source === "simulation" && <span className="ml-2 rounded bg-fuchsia-400/15 px-2 py-0.5 text-xs text-fuchsia-200">SIMULATED</span>}</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">{incident.title}</h1>
          <p className="mt-2 text-zinc-400">{incident.description}</p>
        </div>
        <div className="flex gap-2">
          <SeverityBadge severity={incident.severity} />
          <span className={`inline-block rounded-full px-3 py-1 text-sm font-medium ${getStatusColor(incident.status)}`}>
            {incident.status}
          </span>
        </div>
      </div>

      {/* Overview */}
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-5">
          <h2 className="text-sm font-medium text-zinc-400">Affected Resources</h2>
          <div className="mt-3 space-y-2">
            {incident.affected_service && (
              <div className="flex items-center gap-2 text-sm">
                <Server size={14} className="text-zinc-500" />
                <span className="text-zinc-300">{incident.affected_service}</span>
              </div>
            )}
            {incident.affected_host && (
              <p className="text-sm text-zinc-400">Host: {incident.affected_host}</p>
            )}
            {!incident.affected_service && !incident.affected_host && (
              <p className="text-sm text-zinc-500">No resource information available</p>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-5">
          <h2 className="text-sm font-medium text-zinc-400">Timeline</h2>
          <div className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-zinc-500">First detected:</span>
              <span className="text-zinc-300">{formatTimestamp(incident.first_detected_at)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Last observed:</span>
              <span className="text-zinc-300">{formatTimestamp(incident.last_observed_at)}</span>
            </div>
            {incident.resolved_at && (
              <div className="flex justify-between">
                <span className="text-zinc-500">Resolved:</span>
                <span className="text-zinc-300">{formatTimestamp(incident.resolved_at)}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900/40 p-5">
        <h2 className="font-medium">Actions</h2>
        <div className="mt-4 rounded-lg border border-cyan-400/20 bg-cyan-400/5 p-4">
          <label className="block text-sm text-zinc-300">Investigate with AI</label>
          <div className="mt-2 flex gap-2"><input value={investigationQuestion} onChange={(event) => setInvestigationQuestion(event.target.value)} className="min-w-0 flex-1 rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" /><button onClick={() => investigateMutation.mutate()} disabled={investigateMutation.isPending || !investigationQuestion.trim()} className="rounded-md bg-cyan-400 px-4 py-2 text-sm font-medium text-zinc-950 disabled:opacity-50">{investigateMutation.isPending ? "Investigating…" : "Investigate"}</button></div>
          {investigateMutation.isError && <p className="mt-2 text-sm text-red-300">{(investigateMutation.error as Error).message}</p>}
          <p className="mt-2 text-xs text-zinc-500">The investigation uses this incident's timeline, evidence, telemetry and indexed documentation. Recommendations are not executed automatically.</p>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {/* Update Status */}
          <div>
            <label className="block text-sm text-zinc-400">Change Status</label>
            <div className="mt-2 flex gap-2">
              <select
                value={newStatus}
                onChange={(e) => setNewStatus(e.target.value as IncidentStatus)}
                className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-sm outline-none focus:border-cyan-400/50"
                disabled={incident.status === "CLOSED"}
              >
                <option value="">Select status...</option>
                {validNextStatuses.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
              <button
                onClick={() => {
                  if (newStatus) {
                    updateStatusMutation.mutate({ status: newStatus, note: note || undefined });
                  }
                }}
                disabled={!newStatus || updateStatusMutation.isPending}
                className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Update
              </button>
            </div>
            {incident.status === "CLOSED" && (
              <p className="mt-1 text-xs text-zinc-500">Closed incidents cannot be modified</p>
            )}
          </div>

          {/* Update Severity */}
          <div>
            <label className="block text-sm text-zinc-400">Change Severity</label>
            <div className="mt-2 flex gap-2">
              <select
                value={newSeverity}
                onChange={(e) => setNewSeverity(e.target.value as IncidentSeverity)}
                className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-sm outline-none focus:border-cyan-400/50"
                disabled={incident.status === "CLOSED"}
              >
                <option value="">Select severity...</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="HIGH">HIGH</option>
                <option value="CRITICAL">CRITICAL</option>
              </select>
              <button
                onClick={() => {
                  if (newSeverity) {
                    updateSeverityMutation.mutate({ severity: newSeverity, note: note || undefined });
                  }
                }}
                disabled={!newSeverity || updateSeverityMutation.isPending}
                className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Update
              </button>
            </div>
          </div>
        </div>

        {/* Note for updates */}
        {(newStatus || newSeverity) && (
          <div className="mt-3">
            <label className="block text-sm text-zinc-400">Optional note</label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Add context for this change..."
              className="mt-1 w-full rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-sm outline-none focus:border-cyan-400/50"
            />
          </div>
        )}

        {/* Add Note */}
        <div className="mt-4 border-t border-zinc-800 pt-4">
          <label className="block text-sm text-zinc-400">Add Note</label>
          <div className="mt-2 flex gap-2">
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Add investigation notes..."
              className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-sm outline-none focus:border-cyan-400/50"
              onKeyDown={(e) => {
                if (e.key === "Enter" && note.trim()) {
                  addNoteMutation.mutate(note.trim());
                }
              }}
            />
            <button
              onClick={() => {
                if (note.trim()) {
                  addNoteMutation.mutate(note.trim());
                }
              }}
              disabled={!note.trim() || addNoteMutation.isPending}
              className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Add Note
            </button>
          </div>
        </div>

        {/* Error messages */}
        {(updateStatusMutation.isError || updateSeverityMutation.isError || addNoteMutation.isError) && (
          <div className="mt-3 rounded-lg border border-red-400/25 bg-red-400/10 p-3 text-sm text-red-200">
            {updateStatusMutation.error?.message || updateSeverityMutation.error?.message || addNoteMutation.error?.message}
          </div>
        )}
      </div>

      {/* Evidence */}
      {evidence.length > 0 && (
        <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900/40 p-5">
          <h2 className="font-medium">Evidence</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {evidence.map((item) => (
              <div key={item.id} className="rounded-lg border border-zinc-800 bg-zinc-900/80 p-3">
                <div className="flex items-start justify-between">
                  <p className="text-sm font-medium text-zinc-300">{item.evidence_type.replace(/_/g, " ")}</p>
                  <span className="text-xs text-zinc-500">{item.source}</span>
                </div>
                {item.metric_name && (
                  <div className="mt-2 flex items-baseline gap-2">
                    <span className="text-xs text-zinc-500">{item.metric_name}:</span>
                    <span className="text-sm text-zinc-300">
                      {item.metric_value !== null ? `${item.metric_value.toFixed(2)} ${item.unit || ""}` : "N/A"}
                    </span>
                  </div>
                )}
                {item.evidence_metadata?.threshold !== undefined && <p className="mt-1 text-xs text-zinc-500">Threshold: {String(item.evidence_metadata.threshold)}{item.unit && !["boolean", "failed"].includes(item.unit) ? ` ${item.unit}` : ""}</p>}
                {!item.metric_name && item.evidence_metadata && <p className="mt-2 text-sm text-zinc-300">{Object.entries(item.evidence_metadata).filter(([key]) => !["simulated", "labels"].includes(key)).map(([key, value]) => `${key.replaceAll("_", " ")}: ${typeof value === "string" ? value : JSON.stringify(value)}`).join(" · ")}</p>}
                {item.resource_identifier && (
                  <p className="mt-1 text-xs text-zinc-500">Resource: {item.resource_identifier}</p>
                )}
                <p className="mt-2 text-xs text-zinc-600">
                  {item.observed_at ? formatTimestamp(item.observed_at) : `Collected ${formatTimestamp(item.collected_at)}`}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Event Timeline */}
      <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900/40 p-5">
        <h2 className="font-medium">Event Timeline</h2>
        <div className="mt-4 space-y-3">
          {events.length === 0 ? (
            <p className="text-sm text-zinc-500">No events recorded</p>
          ) : (
            events.map((event, index) => (
              <div key={event.id} className="flex gap-3">
                <div className="relative flex flex-col items-center">
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-zinc-800 text-zinc-400">
                    <Clock size={12} />
                  </div>
                  {index < events.length - 1 && (
                    <div className="w-px flex-1 bg-zinc-800 mt-2"></div>
                  )}
                </div>
                <div className="flex-1 pb-4">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm text-zinc-300">{event.description}</p>
                    <span className="text-xs text-zinc-600 whitespace-nowrap">
                      {formatTimestamp(event.created_at)}
                    </span>
                  </div>
                  <div className="mt-1 flex gap-3 text-xs text-zinc-500">
                    <span>Type: {event.event_type.replace(/_/g, " ")}</span>
                    <span>Source: {event.source}</span>
                  </div>
                  {event.previous_status && event.new_status && (
                    <p className="mt-1 text-xs text-zinc-600">
                      {event.previous_status} → {event.new_status}
                    </p>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
}
