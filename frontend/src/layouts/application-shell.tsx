import { Activity, Bot, BookOpen, FlaskConical, Gauge, LogOut, Settings, Siren, type LucideIcon } from "lucide-react";
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
  return <div className="app-shell min-h-screen text-slate-100 md:grid md:grid-cols-[16rem_1fr]">
    <aside className="app-sidebar border-b p-4 md:border-b-0 md:border-r">
       <Link className="mb-8 flex items-center gap-3 rounded-xl px-3 py-2" to="/"><img src="/brand/kibolens-mark.svg" alt="KiboLens" className="h-9 w-9" /><span><strong className="block font-semibold tracking-tight">KiboLens</strong><span className="text-[10px] font-semibold uppercase tracking-[.18em] text-slate-500">AI-SRE control plane</span></span></Link>
      <nav className="grid grid-cols-2 gap-1.5 md:grid-cols-1">{navigation.map(({ icon: Icon, label, path }) => <NavLink className={({ isActive }) => `group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition ${isActive ? "bg-cyan-400/10 text-cyan-200 shadow-[inset_3px_0_0_#22d3ee]" : "text-slate-400 hover:bg-slate-800/70 hover:text-slate-100"}`} key={label} to={path}><Icon size={17} className="transition group-hover:text-cyan-300" />{label}</NavLink>)}</nav>
       <div className="mt-8 border-t border-slate-800/80 pt-4 text-sm"><p className="px-3 text-[10px] font-semibold uppercase tracking-[.16em] text-slate-600">Signed in as</p><p className="mt-1 truncate px-3 text-slate-300">{user?.username}</p><button className="mt-3 inline-flex items-center gap-2 rounded-lg px-3 py-2 text-slate-400 transition hover:bg-red-400/10 hover:text-red-200" onClick={() => setSignOutOpen(true)}><LogOut size={15} />Sign out</button></div>
    </aside>
    <main className="app-main">{children}</main>
    <ConfirmDialog open={signOutOpen} title="Sign out of KiboLens?" description="Your current session will end and you will need to verify your identity again to continue." confirmLabel="Sign out" destructive busy={signingOut} onCancel={() => setSignOutOpen(false)} onConfirm={() => void confirmSignOut()} />
  </div>;
}
