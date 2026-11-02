import type { Conversation, Message } from "../types/conversations";
import { apiRequest } from "./http";

interface InvestigationResponse {
  question: string;
  findings: string | null;
  evidence: Record<string, unknown>;
  data_sources: string[];
  error: string | null;
  timestamp: string;
  routing_metadata: Record<string, unknown> | null;
}

export const conversationService = {
  list: () => apiRequest<{ items: Conversation[] }>("/conversations"),
  create: (title: string) => apiRequest<Conversation>("/conversations", { method: "POST", body: JSON.stringify({ title }) }),
  rename: (id: string, title: string) => apiRequest<Conversation>(`/conversations/${id}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  remove: (id: string) => apiRequest<void>(`/conversations/${id}`, { method: "DELETE" }),
  messages: (id: string) => apiRequest<{ items: Message[] }>(`/conversations/${id}/messages`),
  addMessage: (id: string, content: string) => apiRequest<Message>(`/conversations/${id}/messages`, { method: "POST", body: JSON.stringify({ content }) }),
  investigate: (id: string, content: string) => apiRequest<InvestigationResponse>(`/conversations/${id}/investigate`, { method: "POST", body: JSON.stringify({ content }) }),
};
