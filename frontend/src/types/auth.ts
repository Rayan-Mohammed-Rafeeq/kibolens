export interface CurrentUser {
  id: string;
  username: string;
  email: string;
  role: string;
  created_at: string;
}

export interface LoginResponse {
  user: CurrentUser;
  csrf_token: string;
}

export interface LoginStage1Response {
  requires_otp: boolean;
  masked_email: string;
  resend_available_in: number;
}

export interface OTPResendResponse {
  success: boolean;
  masked_email: string;
  resend_available_in: number;
}
