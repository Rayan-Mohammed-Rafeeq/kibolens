import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import { settingsService } from "../services/settings";

export function SettingsPage() {
  const client = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: settingsService.get });
  const [otp, setOtp] = useState("");
  const testEmail = useMutation({ mutationFn: settingsService.testEmail });
  const update = useMutation({
    mutationFn: settingsService.updateNotifications,
    onSuccess: () => client.invalidateQueries({ queryKey: ["settings"] }),
  });
  const verify = useMutation({ mutationFn: settingsService.verifyEmail });
  const confirm = useMutation({
    mutationFn: () => settingsService.confirmEmail(otp),
    onSuccess: () => {
      setOtp("");
      client.invalidateQueries({ queryKey: ["settings"] });
    },
  });
  if (settings.isLoading) return <section className="mx-auto max-w-5xl"><p className="text-zinc-400">Loading settings…</p></section>;
  if (settings.isError || !settings.data) return <section className="mx-auto max-w-5xl"><p className="rounded-lg border border-red-400/25 bg-red-400/10 p-4 text-red-200">Could not load settings: {(settings.error as Error)?.message}</p></section>;
  const data = settings.data;
  const notifications = data.notifications;
  return <section className="mx-auto max-w-5xl">
    <p className="text-sm font-medium text-cyan-300">Operations</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">Settings</h1><p className="mt-2 text-zinc-400">Operational configuration, provider status and account notification controls.</p>
    <div className="mt-6 grid gap-4 md:grid-cols-2">
      <Panel title="AI routing"><p>Order: {data.ai.provider_order.join(" → ")}</p><p>Free-only: {data.ai.free_only ? "enabled" : "disabled"}</p>{Object.entries(data.ai.router.providers).map(([name, provider]) => <div className="mt-3 flex items-center justify-between border-t border-zinc-800 pt-3" key={name}><span>{name}</span><span className={provider.available && provider.api_reachable ? "text-emerald-300" : "text-amber-300"}>{provider.available && provider.api_reachable ? <CheckCircle2 className="inline" size={15} /> : <CircleAlert className="inline" size={15} />} {provider.available ? `${provider.text_models_count} eligible models` : "not configured"}</span></div>)}</Panel>
      <Panel title="Monitoring"><p>Prometheus: {data.monitoring.prometheus_url}</p><p>Stale after: {data.monitoring.stale_after_seconds}s</p><p>Environment: {data.environment}</p></Panel>
      <Panel title="Knowledge Base"><p>Embedding model: {data.documents.embedding_model}</p><p>Vector dimensions: {data.documents.embedding_dimension}</p><p>Maximum upload: {data.documents.max_file_size_mb} MB</p></Panel>
      <Panel title="Authentication"><p>OTP lifetime: {data.authentication.otp_ttl_seconds}s</p><p>Secure cookie: {data.authentication.secure_cookie ? "enabled" : "development mode"}</p><p>Allowed administrators: {data.authentication.allowed_email_count}</p></Panel>
      <Panel title="Incident notifications">
       <p>Account: {notifications.account_email ?? "No account email"}</p>
        <p>Configured server owners: {notifications.configured_recipient_count}</p>
        <p className="text-xs text-zinc-500">Eligible infrastructure incidents are sent to every configured owner independently.</p>
        <p>Delivery: <span className={notifications.delivery_status === "ready" ? "text-emerald-300" : "text-amber-300"}>{notifications.delivery_status}</span></p>
        {notifications.email_verified ? <p className="text-emerald-300">Account email verified.</p> : <div className="mt-3 space-y-2"><p className="text-amber-200">Verify your account email before receiving incident notifications.</p><button onClick={() => verify.mutate()} disabled={verify.isPending} className="rounded-md border border-zinc-700 px-3 py-2 text-sm">{verify.isPending ? "Sending…" : "Send verification code"}</button>{verify.isSuccess && <div className="flex gap-2"><input aria-label="Email verification code" value={otp} onChange={(event) => setOtp(event.target.value)} className="w-40 rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" placeholder="6-digit code" /><button onClick={() => confirm.mutate()} disabled={confirm.isPending || otp.length !== 6} className="rounded-md bg-cyan-400 px-3 py-2 text-sm text-zinc-950">Verify</button></div>}</div>}
        <label className="mt-4 flex items-center gap-2"><input type="checkbox" checked={notifications.incident_notifications_enabled} onChange={(event) => update.mutate({ enabled: event.target.checked, minimum_severity: notifications.minimum_severity, recovery_enabled: notifications.recovery_notifications_enabled })} />Send incident notifications to my account email</label>
        <label className="mt-2 flex items-center gap-2">Minimum severity<select value={notifications.minimum_severity} onChange={(event) => update.mutate({ enabled: notifications.incident_notifications_enabled, minimum_severity: event.target.value, recovery_enabled: notifications.recovery_notifications_enabled })} className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1"><option>INFO</option><option>WARNING</option><option>HIGH</option><option>CRITICAL</option></select></label>
        <label className="mt-2 flex items-center gap-2"><input type="checkbox" checked={notifications.recovery_notifications_enabled} onChange={(event) => update.mutate({ enabled: notifications.incident_notifications_enabled, minimum_severity: notifications.minimum_severity, recovery_enabled: event.target.checked })} />Send recovery notifications</label>
        <button onClick={() => testEmail.mutate()} disabled={testEmail.isPending || notifications.delivery_status !== "ready"} className="mt-4 rounded-md bg-cyan-400 px-3 py-2 text-sm text-zinc-950 disabled:opacity-50">{testEmail.isPending ? "Sending…" : "Send test to my account email"}</button>
        {testEmail.isSuccess && <p className="mt-2 text-xs text-emerald-300">Test email sent.</p>}{testEmail.isError && <p className="mt-2 text-xs text-red-300">{(testEmail.error as Error).message}</p>}
      </Panel>
    </div>
  </section>;
}

function Panel({ title, children }: { title: string; children: ReactNode }) { return <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5"><h2 className="font-medium">{title}</h2><div className="mt-4 space-y-2 text-sm text-zinc-400">{children}</div></section>; }
