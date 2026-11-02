import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, RotateCcw, ShieldCheck, Square } from "lucide-react";
import { useState } from "react";
import { labScenarios, labService, type LabScenario } from "../services/lab";

const physicalScenarioKeys = new Set<LabScenario>(["container-crash", "container-restart-loop", "container-unhealthy", "application-config-failure"]);

export function FailureLabPage() {
  const client = useQueryClient();
  const status = useQuery({ queryKey: ["lab-status"], queryFn: labService.status, refetchInterval: 5000 });
  const [physical, setPhysical] = useState(false);
  const [notifyDemo, setNotifyDemo] = useState(false);
  const start = useMutation({ mutationFn: ({ scenario, physical: usePhysical }: { scenario: LabScenario; physical: boolean }) => labService.start(scenario, usePhysical, notifyDemo), onSuccess: () => client.invalidateQueries({ queryKey: ["lab-status"] }) });
  const stop = useMutation({ mutationFn: labService.stop, onSuccess: () => client.invalidateQueries({ queryKey: ["lab-status"] }) });
  const recover = useMutation({ mutationFn: labService.recover, onSuccess: () => client.invalidateQueries({ queryKey: ["lab-status"] }) });
  const reset = useMutation({ mutationFn: labService.reset, onSuccess: () => client.invalidateQueries({ queryKey: ["lab-status"] }) });
  const active = new Map((status.data ?? []).map((item) => [item.labels?.["kibolens.scenario"] ?? item.labels?.["kibolens.lab.scenario"] ?? item.name.replace("kibolens-lab-", ""), item]));

  return <section className="mx-auto max-w-6xl">
    <p className="text-sm font-medium text-cyan-300">Controlled experiments</p>
    <h1 className="mt-2 text-3xl font-semibold tracking-tight">Failure Lab / Demo Simulation</h1>
    <p className="mt-2 max-w-3xl text-zinc-400">Synthetic scenarios exercise incident creation, notification and AI investigation without stressing production. The optional physical Docker lab is limited to labeled resources.</p>
    <div className="mt-4 flex flex-wrap items-center gap-4 rounded-lg border border-amber-400/20 bg-amber-400/5 p-4 text-sm text-amber-200">
      <ShieldCheck size={17} />
      <span>Administrator-only and CSRF-protected.</span>
      <label className="flex items-center gap-2"><input type="checkbox" checked={notifyDemo} onChange={(event) => setNotifyDemo(event.target.checked)} />Send demo email to configured test recipients</label>
      <label className="flex items-center gap-2"><input type="checkbox" checked={physical} onChange={(event) => setPhysical(event.target.checked)} />Use isolated Docker lab where supported</label>
    </div>
    <div className="mt-6 grid gap-3 md:grid-cols-2">
      {labScenarios.map((scenario) => {
        const item = active.get(scenario);
        const usePhysical = physical && physicalScenarioKeys.has(scenario);
        return <article className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4" key={scenario}>
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="font-medium capitalize">{scenario.replaceAll("-", " ")}</h2>
              <p className="mt-1 text-xs text-zinc-500">{item ? `${item.status}${item.labels?.["kibolens.simulated"] === "true" ? " · SIMULATED" : ""}` : "not started"}</p>
            </div>
            <div className="flex gap-2">
              <button aria-label={`Start ${scenario}`} onClick={() => start.mutate({ scenario, physical: usePhysical })} disabled={Boolean(item) || start.isPending} className="rounded-md bg-cyan-400 p-2 text-zinc-950 disabled:opacity-40"><Play size={15} /></button>
              <button aria-label={`Stop ${scenario}`} onClick={() => stop.mutate(scenario)} disabled={!item || stop.isPending} className="rounded-md border border-zinc-700 p-2 text-zinc-300 disabled:opacity-40"><Square size={15} /></button>
              {scenario === "interview-demo" && <button aria-label="Recover interview demo" onClick={() => recover.mutate()} disabled={recover.isPending} className="rounded-md border border-emerald-400/40 px-2 text-xs text-emerald-300 disabled:opacity-40">Recover</button>}
            </div>
          </div>
          {item?.incident_id && <a className="mt-3 inline-block text-xs text-cyan-300 hover:text-cyan-200" href={`/incidents/${item.incident_id}`}>Open simulated incident →</a>}
          {item?.logs && <pre className="mt-3 max-h-24 overflow-auto whitespace-pre-wrap rounded bg-zinc-950 p-2 text-xs text-zinc-500">{item.logs}</pre>}
        </article>;
      })}
    </div>
    <button onClick={() => reset.mutate()} disabled={reset.isPending} className="mt-6 flex items-center gap-2 rounded-md border border-zinc-700 px-3 py-2 text-sm text-zinc-300"><RotateCcw size={15} />Reset lab and close demo incidents</button>
  </section>;
}
