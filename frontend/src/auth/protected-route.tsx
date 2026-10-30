import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./auth-context";

export function ProtectedRoute() {
  const { user, loading } = useAuth();
  if (loading) return <div className="grid min-h-screen place-items-center bg-zinc-950 text-zinc-400">Restoring secure session…</div>;
  return user ? <Outlet /> : <Navigate to="/login" replace />;
}
