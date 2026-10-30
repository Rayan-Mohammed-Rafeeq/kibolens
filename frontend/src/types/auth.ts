export interface CurrentUser {
  id: string;
  username: string;
  role: string;
  created_at: string;
}

export interface LoginResponse {
  user: CurrentUser;
  csrf_token: string;
}
