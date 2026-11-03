import { Activity, Bot, BookOpen, FlaskConical, Gauge, Settings, Siren, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../auth/auth-context";
import { ConfirmDialog } from "../components/dialog";
import { useState } from "react";

const navigation: Array<{ icon: LucideIcon; label: string; path: string }> = [
  { icon: Gauge, label: "Overview", path: "/" },
  { icon: Bot, label: "AI Chat", path: "/chat" },
  { icon: Activity, label: "Infrastructure", path: "/infrastructure" },
  { icon: Siren, label: "Incidents", path: "/incidents" },
  { icon: FlaskConical, label: "Failure Lab", path: "/failure-lab" },
  { icon: BookOpen, label: "Knowledge Base", path: "/knowledge-base" },
  { icon: Settings, label: "Settings", path: "/settings" },
];

export function ApplicationShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const [signOutOpen, setSignOutOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  async function confirmSignOut() {
    setSigningOut(true);
    try { await logout(); } finally { setSigningOut(false); setSignOutOpen(false); }
  }
  return <div className="min-h-screen bg-zinc-950 text-zinc-100 md:grid md:grid-cols-[15rem_1fr]">
    <aside className="border-b border-zinc-800 bg-zinc-950 p-5 md:border-b-0 md:border-r">
       <Link className="mb-8 flex items-center gap-3" to="/"><img src="/brand/kibolens-mark.svg" alt="KiboLens" className="h-9 w-9" /><span className="font-semibold tracking-tight">KiboLens</span></Link>
      <nav className="grid grid-cols-2 gap-1 md:grid-cols-1">{navigation.map(({ icon: Icon, label, path }) => <NavLink className={({ isActive }) => `flex items-center gap-3 rounded-md px-3 py-2 text-sm ${isActive ? "bg-zinc-800 text-white" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"}`} key={label} to={path}><Icon size={16} />{label}</NavLink>)}</nav>
       <div className="mt-8 border-t border-zinc-800 pt-4 text-sm"><p className="truncate px-3 text-zinc-500">{user?.username}</p><button className="mt-2 px-3 text-zinc-400 hover:text-white" onClick={() => setSignOutOpen(true)}>Sign out</button></div>
    </aside>
    <main className="p-6 md:p-10">{children}</main>
    <ConfirmDialog open={signOutOpen} title="Sign out of KiboLens?" description="Your current session will end and you will need to verify your identity again to continue." confirmLabel="Sign out" destructive busy={signingOut} onCancel={() => setSignOutOpen(false)} onConfirm={() => void confirmSignOut()} />
  </div>;
}
