import { apiRequest } from "./http";
import type {
  Incident,
  IncidentDetail,
  IncidentListResponse,
  IncidentSummary,
  IncidentSeverity,
  IncidentStatus,
  IncidentEvent,
  EvidenceRecord,
} from "../types/incident";

export const incidentsService = {
  summary: () => apiRequest<IncidentSummary>("/incidents/summary"),
  
  list: (params?: {
    page?: number;
    page_size?: number;
    severity?: IncidentSeverity;
    status?: IncidentStatus;
    affected_service?: string;
    search?: string;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.append("page", params.page.toString());
    if (params?.page_size) searchParams.append("page_size", params.page_size.toString());
    if (params?.severity) searchParams.append("severity", params.severity);
    if (params?.status) searchParams.append("status", params.status);
    if (params?.affected_service) searchParams.append("affected_service", params.affected_service);
    if (params?.search) searchParams.append("search", params.search);
    const query = searchParams.toString() ? `?${searchParams}` : "";
    return apiRequest<IncidentListResponse>(`/incidents${query}`);
  },
  
  get: (id: string) => apiRequest<IncidentDetail>(`/incidents/${id}`),
  
  getEvents: (id: string) => apiRequest<IncidentEvent[]>(`/incidents/${id}/events`),
  
  getEvidence: (id: string) => apiRequest<EvidenceRecord[]>(`/incidents/${id}/evidence`),
  
  updateStatus: (id: string, status: IncidentStatus, note?: string) =>
    apiRequest<Incident>(`/incidents/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status, note }),
    }),
  
  updateSeverity: (id: string, severity: IncidentSeverity, note?: string) =>
    apiRequest<Incident>(`/incidents/${id}/severity`, {
      method: "PATCH",
      body: JSON.stringify({ severity, note }),
    }),
  
  addNote: (id: string, note: string) =>
    apiRequest<IncidentEvent>(`/incidents/${id}/notes`, {
      method: "POST",
      body: JSON.stringify({ note }),
    }),
  investigate: (id: string, question: string) =>
    apiRequest<{ conversation_id: string; findings: string | null; error: string | null }>(`/incidents/${id}/investigate`, {
      method: "POST",
      body: JSON.stringify({ content: question }),
    }),
};
