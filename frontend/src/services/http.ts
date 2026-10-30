const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (csrfToken && !["GET", "HEAD"].includes(options.method ?? "GET")) headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(`${apiBaseUrl}${path}`, { ...options, headers, credentials: "include" });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? "KiboLens could not complete that request.");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
