export type IncidentSeverity = 'INFO' | 'WARNING' | 'HIGH' | 'CRITICAL';
export type IncidentStatus = 
  | 'DETECTED' 
  | 'INVESTIGATING' 
  | 'IDENTIFIED' 
  | 'RESOLVING' 
  | 'RESOLVED' 
  | 'CLOSED';

export type EventType =
  | 'INCIDENT_CREATED'
  | 'ALERT_RECEIVED'
  | 'ALERT_REPEATED'
  | 'STATUS_CHANGED'
  | 'SEVERITY_CHANGED'
  | 'EVIDENCE_CAPTURED'
  | 'INCIDENT_RESOLVED'
  | 'INCIDENT_REOPENED'
  | 'NOTE_ADDED'
  | 'INCIDENT_CLOSED';

export type EvidenceType =
  | 'HOST_METRIC'
  | 'CONTAINER_METRIC'
  | 'CONTAINER_STATE'
  | 'PROMETHEUS_ALERT'
  | 'SYSTEM_EVENT'
  | 'LOG_EXCERPT';

export interface Incident {
  id: string;
  incident_number: string;
  title: string;
  description: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  source: string;
  alert_fingerprint: string | null;
  logical_fingerprint: string | null;
  affected_host: string | null;
  affected_service: string | null;
  first_detected_at: string;
  last_observed_at: string;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface IncidentEvent {
  id: string;
  incident_id: string;
  event_type: EventType;
  description: string;
  previous_status: IncidentStatus | null;
  new_status: IncidentStatus | null;
  source: string;
  event_metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface EvidenceRecord {
  id: string;
  incident_id: string;
  evidence_type: EvidenceType;
  source: string;
  resource_identifier: string | null;
  metric_name: string | null;
  metric_value: number | null;
  unit: string | null;
  observed_at: string | null;
  collected_at: string;
  evidence_metadata: Record<string, unknown> | null;
}

export interface IncidentDetail {
  incident: Incident;
  events: IncidentEvent[];
  evidence: EvidenceRecord[];
}

export interface IncidentListResponse {
  incidents: Incident[];
  total: number;
  page: number;
  page_size: number;
}

export interface IncidentSummary {
  total_active: number;
  critical_count: number;
  high_count: number;
  warning_count: number;
  info_count: number;
  recently_resolved_count: number;
  oldest_unresolved: Incident | null;
  latest_incidents: Incident[];
}

export interface IncidentStatusUpdate {
  status: IncidentStatus;
  note?: string;
}

export interface IncidentSeverityUpdate {
  severity: IncidentSeverity;
  note?: string;
}

export interface IncidentNote {
  note: string;
}
