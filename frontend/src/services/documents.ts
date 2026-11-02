import { apiRequest, getCsrfToken } from "./http";

export interface DocumentItem {
  document_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  uploaded_at: string;
  total_chunks: number;
}

export interface SearchResult {
  text: string;
  score: number;
  document_id: string;
  filename: string;
  chunk_index: number;
  file_type: string;
}

export const documentsService = {
  list: () => apiRequest<DocumentItem[]>("/documents/list"),
  search: (query: string) => apiRequest<{ query: string; results: SearchResult[]; count: number }>("/documents/search", {
    method: "POST",
    body: JSON.stringify({ query, limit: 8 }),
  }),
  upload: async (file: File): Promise<{ document_id: string; filename: string; chunks: number; characters: number; uploaded_at: string }> => {
    const response = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? "/api/v1"}/documents/upload`, {
      method: "POST",
      body: (() => { const form = new FormData(); form.append("file", file); return form; })(),
      credentials: "include",
      headers: getCsrfToken() ? { "X-CSRF-Token": getCsrfToken()! } : {},
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null) as { detail?: string } | null;
      throw new Error(body?.detail ?? "Document ingestion failed.");
    }
    return response.json();
  },
  remove: (id: string) => apiRequest<void>(`/documents/${id}`, { method: "DELETE" }),
};
