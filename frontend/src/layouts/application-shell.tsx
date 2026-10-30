import { Activity, Bot, BookOpen, Gauge, Settings, Siren, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

const navigation: Array<{ icon: LucideIcon; label: string }> = [
  { icon: Gauge, label: "Overview" },
  { icon: Bot, label: "AI Chat" },
  { icon: Activity, label: "Infrastructure" },
  { icon: Siren, label: "Incidents" },
  { icon: BookOpen, label: "Knowledge Base" },
  { icon: Settings, label: "Settings" },
];

export function ApplicationShell({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-zinc-950 text-zinc-100 md:grid md:grid-cols-[15rem_1fr]">
    <aside className="border-b border-zinc-800 bg-zinc-950 p-5 md:border-b-0 md:border-r">
      <div className="mb-8 flex items-center gap-3"><div className="rounded-lg bg-cyan-400/15 p-2 text-cyan-300"><Activity size={20} /></div><span className="font-semibold tracking-tight">KiboLens</span></div>
      <nav className="grid grid-cols-2 gap-1 md:grid-cols-1">{navigation.map(({ icon: Icon, label }) => <button className={`flex items-center gap-3 rounded-md px-3 py-2 text-left text-sm ${label === "Overview" ? "bg-zinc-800 text-white" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"}`} key={label}><Icon size={16} />{label}</button>)}</nav>
    </aside>
    <main className="p-6 md:p-10">{children}</main>
  </div>;
}
