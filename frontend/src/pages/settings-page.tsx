import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { settingsService } from "../services/settings";

export function SettingsPage() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: settingsService.get });
  if (settings.isLoading) return <section className="mx-auto max-w-5xl"><p className="text-zinc-400">Loading settings…</p></section>;
  if (settings.isError || !settings.data) return <section className="mx-auto max-w-5xl"><p className="rounded-lg border border-red-400/25 bg-red-400/10 p-4 text-red-200">Could not load settings: {(settings.error as Error)?.message}</p></section>;
  const data = settings.data;
  return <section className="mx-auto max-w-5xl"><p className="text-sm font-medium text-cyan-300">Operations</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">Settings</h1><p className="mt-2 text-zinc-400">Read-only operational configuration and provider status.</p><div className="mt-6 grid gap-4 md:grid-cols-2"><Panel title="AI routing"><p>Order: {data.ai.provider_order.join(" → ")}</p><p>Free-only: {data.ai.free_only ? "enabled" : "disabled"}</p>{Object.entries(data.ai.router.providers).map(([name, provider]) => <div className="mt-3 flex items-center justify-between border-t border-zinc-800 pt-3" key={name}><span>{name}</span><span className={provider.available && provider.api_reachable ? "text-emerald-300" : "text-amber-300"}>{provider.available && provider.api_reachable ? <CheckCircle2 className="inline" size={15} /> : <CircleAlert className="inline" size={15} />} {provider.available ? `${provider.text_models_count} eligible models` : "not configured"}</span></div>)}</Panel><Panel title="Monitoring"><p>Prometheus: {data.monitoring.prometheus_url}</p><p>Stale after: {data.monitoring.stale_after_seconds}s</p><p>Environment: {data.environment}</p></Panel><Panel title="Knowledge Base"><p>Embedding model: {data.documents.embedding_model}</p><p>Vector dimensions: {data.documents.embedding_dimension}</p><p>Maximum upload: {data.documents.max_file_size_mb} MB</p></Panel><Panel title="Authentication"><p>OTP lifetime: {data.authentication.otp_ttl_seconds}s</p><p>Secure cookie: {data.authentication.secure_cookie ? "enabled" : "development mode"}</p><p>Allowed administrators: {data.authentication.allowed_email_count}</p></Panel></div></section>;
}

function Panel({ title, children }: { title: string; children: ReactNode }) { return <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5"><h2 className="font-medium">{title}</h2><div className="mt-4 space-y-2 text-sm text-zinc-400">{children}</div></section>; }
