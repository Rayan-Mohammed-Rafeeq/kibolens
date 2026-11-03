import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, RotateCcw, ShieldCheck, Square } from "lucide-react";
import { useState } from "react";
import { ConfirmDialog } from "../components/dialog";
import { SeverityBadge } from "../components/severity-badge";
import { labScenarios, labService, type LabScenario } from "../services/lab";

const physicalScenarioKeys = new Set<LabScenario>(["container-crash", "container-restart-loop", "container-unhealthy", "application-config-failure"]);

export function FailureLabPage() {
  const client = useQueryClient();
  const status = useQuery({ queryKey: ["lab-status"], queryFn: labService.status, refetchInterval: 5000 });
  const [physical, setPhysical] = useState(false);
  const [lastResult, setLastResult] = useState<{ name: string; status: string; incident_id?: string; notification?: { status: string; detail?: string } } | null>(null);
  const [resetOpen, setResetOpen] = useState(false);
  const [pendingStop, setPendingStop] = useState<LabScenario | null>(null);
  const scenarios = useQuery({ queryKey: ["lab-scenarios"], queryFn: labService.scenarios, staleTime: 300_000 });
  const start = useMutation({ mutationFn: ({ scenario, physical: usePhysical }: { scenario: LabScenario; physical: boolean }) => labService.start(scenario, usePhysical), onSuccess: (result) => { setLastResult(result); void client.invalidateQueries({ queryKey: ["lab-status"] }); } });
  const stop = useMutation({ mutationFn: labService.stop, onSuccess: () => { setPendingStop(null); return client.invalidateQueries({ queryKey: ["lab-status"] }); } });
  const reset = useMutation({ mutationFn: labService.reset, onSuccess: () => client.invalidateQueries({ queryKey: ["lab-status"] }) });
  const active = new Map((status.data ?? []).map((item) => [item.labels?.["kibolens.scenario"] ?? item.labels?.["kibolens.lab.scenario"] ?? item.name.replace("kibolens-lab-", ""), item]));

  return <section className="mx-auto max-w-6xl">
    <p className="text-sm font-medium text-cyan-300">Controlled experiments</p>
    <h1 className="mt-2 text-3xl font-semibold tracking-tight">Failure Lab / Demo Simulation</h1>
    <p className="mt-2 max-w-3xl text-zinc-400">Controlled experiments exercise incident creation, owner notification and AI investigation without stressing production. Physical Docker scenarios are limited to labeled resources.</p>
    <div className="mt-4 flex flex-wrap items-center gap-4 rounded-lg border border-amber-400/20 bg-amber-400/5 p-4 text-sm text-amber-200">
      <ShieldCheck size={17} />
      <span>Administrator-only and CSRF-protected.</span>
      <span className="text-cyan-200">Eligible experiments automatically notify both configured server owners.</span>
      <label className="flex items-center gap-2"><input type="checkbox" checked={physical} onChange={(event) => setPhysical(event.target.checked)} />Use isolated Docker lab where supported</label>
    </div>
    {lastResult && <div className="mt-4 rounded-lg border border-cyan-400/20 bg-cyan-400/5 p-3 text-sm text-cyan-100">{lastResult.name}: incident {lastResult.incident_id ? "created" : "not created"}; email {lastResult.notification?.status ?? "not requested"}{lastResult.notification?.detail ? ` — ${lastResult.notification.detail}` : ""}.</div>}
    {(start.isError || stop.isError || reset.isError) && <div className="mt-4 rounded-lg border border-red-400/25 bg-red-400/10 p-3 text-sm text-red-200">Failure Lab action failed: {((start.error || stop.error || reset.error) as Error).message}</div>}
    {status.isError && <div className="mt-4 rounded-lg border border-red-400/25 bg-red-400/10 p-3 text-sm text-red-200">Failure Lab status is unavailable: {(status.error as Error).message}</div>}
    <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {labScenarios.map((scenario) => {
        const item = active.get(scenario);
        const usePhysical = physical && physicalScenarioKeys.has(scenario);
        const definition = scenarios.data?.find((entry) => entry.key === scenario);
        return <article className="flex min-h-[235px] flex-col rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 transition-colors hover:border-zinc-700" key={scenario}>
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2"><span className={`h-2.5 w-2.5 rounded-full ${definition?.severity === "CRITICAL" ? "bg-red-400" : definition?.severity === "HIGH" ? "bg-orange-400" : "bg-amber-300"}`} /><h2 className="font-medium text-zinc-100">{definition?.title ?? scenario.replaceAll("-", " ")}</h2></div>
              <p className="mt-2 text-sm leading-5 text-zinc-400">{definition?.description ?? "Controlled Failure Lab experiment."}</p>
              <p className="mt-1 text-xs text-zinc-500">{item ? `${item.status}${item.labels?.["kibolens.simulated"] === "true" ? " · SIMULATED" : ""}` : "not started"}</p>
            </div>
            <div className="flex shrink-0 gap-2">
              <button aria-label={`Start ${scenario}`} onClick={() => start.mutate({ scenario, physical: usePhysical })} disabled={Boolean(item) || start.isPending} className="inline-flex items-center gap-1.5 rounded-md bg-cyan-400 px-2.5 py-2 text-xs font-medium text-zinc-950 transition hover:bg-cyan-300 disabled:opacity-40"><Play size={14} />Start</button>
              <button aria-label={`Stop ${scenario}`} onClick={() => setPendingStop(scenario)} disabled={!item || stop.isPending} className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 px-2.5 py-2 text-xs text-zinc-300 transition hover:border-zinc-500 disabled:opacity-40"><Square size={14} />Stop</button>
            </div>
          </div>
          <div className="mt-auto pt-4">{definition && <SeverityBadge severity={definition.severity} />}
          {item?.incident_id && <a className="mt-3 inline-block text-xs text-cyan-300 hover:text-cyan-200" href={`/incidents/${item.incident_id}`}>Open simulated incident →</a>}
          {item?.notification && <div className="mt-3 space-y-1 text-xs"><p className="text-zinc-500">Owner notification: {item.notification.status}</p>{item.notification.deliveries?.map((delivery) => <p className={delivery.status === "failed" ? "text-red-300" : delivery.status === "pending" ? "text-amber-200" : "text-emerald-300"} key={delivery.recipient}>{delivery.recipient}: {delivery.status}{delivery.detail ? ` — ${delivery.detail}` : ""}</p>)}</div>}
          {(item?.evidence?.length || item?.logs) ? <pre className="mt-3 max-h-24 overflow-auto whitespace-pre-wrap rounded bg-zinc-950 p-2 text-xs text-zinc-500">{item.evidence?.filter((evidence) => evidence.metric_name).map((evidence) => `${evidence.metric_name}: ${evidence.value} ${evidence.unit ?? ""}`).join(" · ") || item.logs}</pre> : null}</div>
        </article>;
      })}
    </div>
    <button onClick={() => setResetOpen(true)} disabled={reset.isPending} className="mt-6 flex items-center gap-2 rounded-md border border-red-400/30 px-3 py-2 text-sm text-red-200 transition hover:border-red-300"><RotateCcw size={15} />Reset lab and close lab incidents</button>
    <ConfirmDialog open={Boolean(pendingStop)} title="Stop Failure Lab experiment?" description={`Stop the ${pendingStop?.replaceAll("-", " ") ?? "selected"} experiment and mark its synthetic resource as recovering. The associated evidence remains available for review.`} confirmLabel="Stop experiment" destructive busy={stop.isPending} onCancel={() => setPendingStop(null)} onConfirm={() => { if (pendingStop) stop.mutate(pendingStop); }} />
    <ConfirmDialog open={resetOpen} title="Reset Failure Lab?" description="This stops and removes only labeled Failure Lab containers and closes their lab incidents. Production resources are not affected." confirmLabel="Reset lab" destructive busy={reset.isPending} onCancel={() => setResetOpen(false)} onConfirm={() => reset.mutate(undefined, { onSuccess: () => setResetOpen(false) })} />
  </section>;
}
