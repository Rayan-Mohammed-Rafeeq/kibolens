import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { CurrentUser } from "../types/auth";
import { getCurrentUser, login as loginRequest, logout as logoutRequest, refreshCsrfToken } from "../services/auth";

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function restoreSession() {
      try {
        const currentUser = await getCurrentUser();
        await refreshCsrfToken();
        setUser(currentUser);
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    }
    void restoreSession();
  }, []);

  async function login(username: string, password: string) {
    const currentUser = await loginRequest(username, password);
    setUser(currentUser);
  }

  async function logout() {
    await logoutRequest();
    setUser(null);
  }

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider.");
  return context;
}
