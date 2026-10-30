import type { HealthResponse } from "../types/health";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${apiBaseUrl}/health`);
  if (!response.ok) throw new Error("The KiboLens API is unavailable.");
  return response.json() as Promise<HealthResponse>;
}
