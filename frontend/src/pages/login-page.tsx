import { Eye, EyeOff, ShieldCheck } from "lucide-react";
import { FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/auth-context";

export function LoginPage() {
  const { user, login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  if (user) return <Navigate to="/chat" replace />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try { await login(username, password); } catch (cause) { setError(cause instanceof Error ? cause.message : "Login failed."); } finally { setSubmitting(false); }
  }

  return <main className="grid min-h-screen place-items-center bg-zinc-950 p-6"><form className="w-full max-w-sm rounded-2xl border border-zinc-800 bg-zinc-900/60 p-7 shadow-2xl" onSubmit={submit}><div className="mb-7"><div className="mb-4 inline-flex rounded-lg bg-cyan-400/15 p-2 text-cyan-300"><ShieldCheck /></div><h1 className="text-2xl font-semibold">Welcome to KiboLens</h1><p className="mt-2 text-sm text-zinc-400">Sign in to your private infrastructure workspace.</p></div><label className="block text-sm font-medium">Username<input aria-label="Username" className="mt-2 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2.5 outline-none focus:border-cyan-400" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label><label className="mt-4 block text-sm font-medium">Password<div className="relative mt-2"><input aria-label="Password" className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2.5 pr-11 outline-none focus:border-cyan-400" value={password} onChange={(event) => setPassword(event.target.value)} type={visible ? "text" : "password"} autoComplete="current-password" required /><button className="absolute inset-y-0 right-0 px-3 text-zinc-400" type="button" aria-label="Toggle password visibility" onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></label>{error && <p className="mt-4 rounded-md bg-red-400/10 p-3 text-sm text-red-300" role="alert">{error}</p>}<button className="mt-6 w-full rounded-md bg-cyan-400 px-4 py-2.5 font-medium text-zinc-950 disabled:opacity-60" disabled={submitting}>{submitting ? "Signing in…" : "Sign in"}</button></form></main>;
}
