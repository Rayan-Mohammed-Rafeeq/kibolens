import type { CurrentUser, LoginResponse } from "../types/auth";
import { apiRequest, setCsrfToken } from "./http";

export async function login(username: string, password: string): Promise<CurrentUser> {
  const response = await apiRequest<LoginResponse>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
  setCsrfToken(response.csrf_token);
  return response.user;
}

export async function getCurrentUser(): Promise<CurrentUser> {
  return apiRequest<CurrentUser>("/auth/me");
}

export async function refreshCsrfToken(): Promise<void> {
  const response = await apiRequest<{ csrf_token: string }>("/auth/csrf");
  setCsrfToken(response.csrf_token);
}

export async function logout(): Promise<void> {
  await apiRequest<void>("/auth/logout", { method: "POST" });
  setCsrfToken(null);
}
