import { Activity, Bot, BookOpen, Gauge, Settings, Siren, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../auth/auth-context";

const navigation: Array<{ icon: LucideIcon; label: string; path: string }> = [
  { icon: Gauge, label: "Overview", path: "/" },
  { icon: Bot, label: "AI Chat", path: "/chat" },
  { icon: Activity, label: "Infrastructure", path: "/infrastructure" },
  { icon: Siren, label: "Incidents", path: "/incidents" },
  { icon: BookOpen, label: "Knowledge Base", path: "/knowledge-base" },
  { icon: Settings, label: "Settings", path: "/settings" },
];

export function ApplicationShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  return <div className="min-h-screen bg-zinc-950 text-zinc-100 md:grid md:grid-cols-[15rem_1fr]">
    <aside className="border-b border-zinc-800 bg-zinc-950 p-5 md:border-b-0 md:border-r">
      <Link className="mb-8 flex items-center gap-3" to="/"><div className="rounded-lg bg-cyan-400/15 p-2 text-cyan-300"><Activity size={20} /></div><span className="font-semibold tracking-tight">KiboLens</span></Link>
      <nav className="grid grid-cols-2 gap-1 md:grid-cols-1">{navigation.map(({ icon: Icon, label, path }) => <NavLink className={({ isActive }) => `flex items-center gap-3 rounded-md px-3 py-2 text-sm ${isActive ? "bg-zinc-800 text-white" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"}`} key={label} to={path}><Icon size={16} />{label}</NavLink>)}</nav>
      <div className="mt-8 border-t border-zinc-800 pt-4 text-sm"><p className="truncate px-3 text-zinc-500">{user?.username}</p><button className="mt-2 px-3 text-zinc-400 hover:text-white" onClick={() => void logout()}>Sign out</button></div>
    </aside>
    <main className="p-6 md:p-10">{children}</main>
  </div>;
}
