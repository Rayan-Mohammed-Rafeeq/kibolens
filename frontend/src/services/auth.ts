import type { CurrentUser, LoginResponse, LoginStage1Response, OTPResendResponse } from "../types/auth";
import { apiRequest, setCsrfToken } from "./http";

export async function loginStage1(email: string, password: string): Promise<LoginStage1Response> {
  return apiRequest<LoginStage1Response>("/auth/login", { 
    method: "POST", 
    body: JSON.stringify({ email, password }) 
  });
}

export async function verifyOtp(email: string, otp: string): Promise<CurrentUser> {
  const response = await apiRequest<LoginResponse>("/auth/verify-otp", { 
    method: "POST", 
    body: JSON.stringify({ email, otp }) 
  });
  setCsrfToken(response.csrf_token);
  return response.user;
}

export async function resendOtp(email: string): Promise<OTPResendResponse> {
  return apiRequest<OTPResendResponse>("/auth/resend-otp", { 
    method: "POST", 
    body: JSON.stringify({ email }) 
  });
}

export async function login(username: string, password: string): Promise<CurrentUser> {
  // Legacy method - kept for backward compatibility during transition
  // Will be deprecated once frontend fully switches to two-stage flow
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
