import type {
  Incident,
  IncidentDetail,
  IncidentEvent,
  IncidentListResponse,
  IncidentNote,
  IncidentSeverity,
  IncidentSeverityUpdate,
  IncidentStatus,
  IncidentStatusUpdate,
  IncidentSummary,
  EvidenceRecord,
} from '../types/incident';

const BASE_URL = '/api/v1/incidents';

async function fetchWithAuth(url: string, options: RequestInit = {}) {
  const response = await fetch(url, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'Request failed');
  }

  return response.json();
}

export async function getIncidentSummary(): Promise<IncidentSummary> {
  return fetchWithAuth(`${BASE_URL}/summary`);
}

export async function listIncidents(params: {
  page?: number;
  page_size?: number;
  severity?: IncidentSeverity;
  status?: IncidentStatus;
  affected_service?: string;
  search?: string;
}): Promise<IncidentListResponse> {
  const searchParams = new URLSearchParams();
  
  if (params.page) searchParams.append('page', params.page.toString());
  if (params.page_size) searchParams.append('page_size', params.page_size.toString());
  if (params.severity) searchParams.append('severity', params.severity);
  if (params.status) searchParams.append('status', params.status);
  if (params.affected_service) searchParams.append('affected_service', params.affected_service);
  if (params.search) searchParams.append('search', params.search);

  const url = searchParams.toString() ? `${BASE_URL}?${searchParams}` : BASE_URL;
  return fetchWithAuth(url);
}

export async function getIncidentDetail(incidentId: string): Promise<IncidentDetail> {
  return fetchWithAuth(`${BASE_URL}/${incidentId}`);
}

export async function getIncidentEvents(incidentId: string): Promise<IncidentEvent[]> {
  return fetchWithAuth(`${BASE_URL}/${incidentId}/events`);
}

export async function getIncidentEvidence(incidentId: string): Promise<EvidenceRecord[]> {
  return fetchWithAuth(`${BASE_URL}/${incidentId}/evidence`);
}

export async function updateIncidentStatus(
  incidentId: string,
  update: IncidentStatusUpdate
): Promise<Incident> {
  const csrfToken = sessionStorage.getItem('csrf_token');
  return fetchWithAuth(`${BASE_URL}/${incidentId}/status`, {
    method: 'PATCH',
    headers: {
      'X-CSRF-Token': csrfToken || '',
    },
    body: JSON.stringify(update),
  });
}

export async function updateIncidentSeverity(
  incidentId: string,
  update: IncidentSeverityUpdate
): Promise<Incident> {
  const csrfToken = sessionStorage.getItem('csrf_token');
  return fetchWithAuth(`${BASE_URL}/${incidentId}/severity`, {
    method: 'PATCH',
    headers: {
      'X-CSRF-Token': csrfToken || '',
    },
    body: JSON.stringify(update),
  });
}

export async function addIncidentNote(
  incidentId: string,
  note: IncidentNote
): Promise<IncidentEvent> {
  const csrfToken = sessionStorage.getItem('csrf_token');
  return fetchWithAuth(`${BASE_URL}/${incidentId}/notes`, {
    method: 'POST',
    headers: {
      'X-CSRF-Token': csrfToken || '',
    },
    body: JSON.stringify(note),
  });
}
