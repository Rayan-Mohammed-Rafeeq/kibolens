import { Eye, EyeOff, Mail } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/auth-context";
import { loginStage1, resendOtp, verifyOtp } from "../services/auth";

type LoginStage = "credentials" | "otp";

export function LoginPage() {
  const { user } = useAuth();
  const [stage, setStage] = useState<LoginStage>("credentials");
  
  // Stage 1: Credentials
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  
  // Stage 2: OTP
  const [otp, setOtp] = useState("");
  const [maskedEmail, setMaskedEmail] = useState("");
  const [resendCooldown, setResendCooldown] = useState(0);
  
  // Common
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  
  // Cooldown timer
  useEffect(() => {
    if (resendCooldown > 0) {
      const timer = setInterval(() => {
        setResendCooldown(prev => Math.max(0, prev - 1));
      }, 1000);
      return () => clearInterval(timer);
    }
  }, [resendCooldown]);
  
  // Redirect if already logged in
  if (user) return <Navigate to="/chat" replace />;
  
  async function handleCredentialsSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    
    try {
      const response = await loginStage1(email, password);
      setMaskedEmail(response.masked_email);
      setResendCooldown(response.resend_available_in);
      setStage("otp");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Login failed.");
    } finally {
      setSubmitting(false);
    }
  }
  
  async function handleOtpSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    
    try {
      await verifyOtp(email, otp);
      // Auth context will update automatically via getCurrentUser
      window.location.href = "/chat";
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Verification failed.");
    } finally {
      setSubmitting(false);
    }
  }
  
  async function handleResendOtp() {
    setError(null);
    setSubmitting(true);
    
    try {
      const response = await resendOtp(email);
      if (response.success) {
        setResendCooldown(response.resend_available_in);
        setError(null);
      } else {
        setResendCooldown(response.resend_available_in);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to resend code.");
    } finally {
      setSubmitting(false);
    }
  }
  
  function handleBackToCredentials() {
    setStage("credentials");
    setOtp("");
    setError(null);
  }
  
  return (
    <main className="relative grid min-h-screen place-items-center overflow-hidden bg-[#070b14] p-6">
      <div className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-cyan-400/10 blur-3xl" /><div className="pointer-events-none absolute -bottom-40 -right-24 h-96 w-96 rounded-full bg-blue-500/10 blur-3xl" />
      <div className="relative w-full max-w-md rounded-2xl border border-slate-700/50 bg-slate-900/75 p-8 shadow-2xl shadow-black/40 backdrop-blur-xl">
        {/* Header */}
        <div className="mb-7">
          <img src="/brand/kibolens-wordmark.svg" alt="KiboLens" className="mb-5 h-12 w-auto" />
           <p className="page-eyebrow">Secure operations workspace</p><h1 className="mt-4 text-3xl font-semibold tracking-tight">
            {stage === "credentials" ? "Welcome to KiboLens" : "Verify your identity"}
          </h1>
          <p className="mt-2 text-sm text-zinc-400">
            {stage === "credentials" 
              ? "Sign in to your private infrastructure workspace."
              : `Enter the 6-digit code sent to ${maskedEmail}`
            }
          </p>
        </div>
        
        {/* Stage 1: Email and Password */}
        {stage === "credentials" && (
          <form onSubmit={handleCredentialsSubmit}>
            <label className="block text-sm font-medium">
              Email address
              <div className="relative mt-2">
                <input
                  aria-label="Email"
                   className="field-control w-full px-3 py-2.5 pl-10"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={17} />
              </div>
            </label>
            
            <label className="mt-4 block text-sm font-medium">
              Password
              <div className="relative mt-2">
                <input
                  aria-label="Password"
                   className="field-control w-full px-3 py-2.5 pr-11"
                  type={passwordVisible ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
                <button
                  className="absolute inset-y-0 right-0 px-3 text-zinc-400 hover:text-zinc-300"
                  type="button"
                  aria-label="Toggle password visibility"
                  onClick={() => setPasswordVisible(!passwordVisible)}
                >
                  {passwordVisible ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </label>
            
            {error && (
              <p className="mt-4 rounded-md bg-red-400/10 p-3 text-sm text-red-300" role="alert">
                {error}
              </p>
            )}
            
            <button
               className="btn-primary mt-6 w-full py-3"
              disabled={submitting}
            >
              {submitting ? "Sending code…" : "Send verification code"}
            </button>
          </form>
        )}
        
        {/* Stage 2: OTP Verification */}
        {stage === "otp" && (
          <form onSubmit={handleOtpSubmit}>
            <label className="block text-sm font-medium">
              Verification code
              <input
                aria-label="6-digit verification code"
                 className="field-control mt-2 w-full px-3 py-2.5 text-center text-2xl font-mono tracking-widest"
                type="text"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
                autoComplete="one-time-code"
                autoFocus
                required
              />
            </label>
            
            <p className="mt-3 text-center text-xs text-zinc-500">
              Code expires in 5 minutes
            </p>
            
            {error && (
              <p className="mt-4 rounded-md bg-red-400/10 p-3 text-sm text-red-300" role="alert">
                {error}
              </p>
            )}
            
            <button
               className="btn-primary mt-6 w-full py-3"
              disabled={submitting || otp.length !== 6}
            >
              {submitting ? "Verifying…" : "Verify and sign in"}
            </button>
            
            <div className="mt-4 flex items-center justify-between text-sm">
              <button
                type="button"
                className="text-zinc-400 hover:text-zinc-300"
                onClick={handleBackToCredentials}
              >
                ← Back
              </button>
              
              <button
                type="button"
                className="text-cyan-400 hover:text-cyan-300 disabled:text-zinc-600 disabled:cursor-not-allowed"
                onClick={handleResendOtp}
                disabled={submitting || resendCooldown > 0}
              >
                {resendCooldown > 0 
                  ? `Resend in ${resendCooldown}s` 
                  : "Resend code"
                }
              </button>
            </div>
          </form>
        )}
      </div>
    </main>
  );
}
