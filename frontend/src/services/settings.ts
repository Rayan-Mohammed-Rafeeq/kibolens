import { apiRequest } from "./http";

export interface SettingsSummary {
  environment: string;
  monitoring: { prometheus_url: string; stale_after_seconds: number };
  ai: { provider_order: string[]; free_only: boolean; paid_models_allowed: boolean; router: { providers: Record<string, { available: boolean; api_reachable: boolean; text_models_count: number }> } };
  documents: { max_file_size_mb: number; embedding_model: string; embedding_dimension: number };
  authentication: { otp_ttl_seconds: number; secure_cookie: boolean; allowed_email_count: number };
  notifications?: { configured_recipient_count?: number; test_recipient_count?: number };
}

export const settingsService = {
  get: () => apiRequest<SettingsSummary>("/settings"),
  testEmail: (recipient?: string) => apiRequest<{ status: string; recipient: string }>("/settings/test-email", { method: "POST", body: JSON.stringify({ recipient: recipient || undefined }) }),
};
