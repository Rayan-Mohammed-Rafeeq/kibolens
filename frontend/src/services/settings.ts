import { apiRequest } from "./http";

export interface SettingsSummary {
  environment: string;
  monitoring: { prometheus_url: string; stale_after_seconds: number };
  ai: { provider_order: string[]; free_only: boolean; paid_models_allowed: boolean; router: { providers: Record<string, { available: boolean; api_reachable: boolean; text_models_count: number }> } };
  documents: { max_file_size_mb: number; embedding_model: string; embedding_dimension: number };
  authentication: { otp_ttl_seconds: number; secure_cookie: boolean; allowed_email_count: number };
  notifications: {
    configured_recipient_count: number;
    test_recipient_count: number;
    provider_configured: boolean;
    account_email: string | null;
    email_verified: boolean;
    incident_notifications_enabled: boolean;
    minimum_severity: "INFO" | "WARNING" | "HIGH" | "CRITICAL";
    recovery_notifications_enabled: boolean;
    delivery_status: "ready" | "email_not_verified" | "resend_not_configured";
  };
}

export const settingsService = {
  get: () => apiRequest<SettingsSummary>("/settings"),
  updateNotifications: (payload: { enabled: boolean; minimum_severity: string; recovery_enabled: boolean }) => apiRequest<{ enabled: boolean; minimum_severity: string; recovery_enabled: boolean }>("/settings/notifications", { method: "PATCH", body: JSON.stringify(payload) }),
  verifyEmail: () => apiRequest<{ status: string }>("/settings/verify-email", { method: "POST", body: "{}" }),
  confirmEmail: (otp: string) => apiRequest<{ status: string }>("/settings/verify-email/confirm", { method: "POST", body: JSON.stringify({ otp }) }),
  testEmail: () => apiRequest<{ status: string; recipient: string }>("/settings/test-email", { method: "POST", body: "{}" }),
};
