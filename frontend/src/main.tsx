import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import { AuthProvider } from "./auth/auth-context";
import { ProtectedRoute } from "./auth/protected-route";
import { ApplicationShell } from "./layouts/application-shell";
import { ChatPage } from "./pages/chat-page";
import { ComingSoonPage } from "./pages/coming-soon-page";
import { LoginPage } from "./pages/login-page";
import { OverviewPage } from "./pages/overview-page";

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(<StrictMode><QueryClientProvider client={queryClient}><BrowserRouter><AuthProvider><Routes><Route path="/login" element={<LoginPage />} /><Route element={<ProtectedRoute />}><Route element={<ApplicationShell><OverviewPage /></ApplicationShell>} path="/" /><Route element={<ApplicationShell><ChatPage /></ApplicationShell>} path="/chat" /><Route element={<ApplicationShell><ComingSoonPage title="Infrastructure" /></ApplicationShell>} path="/infrastructure" /><Route element={<ApplicationShell><ComingSoonPage title="Incidents" /></ApplicationShell>} path="/incidents" /><Route element={<ApplicationShell><ComingSoonPage title="Knowledge Base" /></ApplicationShell>} path="/knowledge-base" /><Route element={<ApplicationShell><ComingSoonPage title="Settings" /></ApplicationShell>} path="/settings" /></Route></Routes></AuthProvider></BrowserRouter></QueryClientProvider></StrictMode>);
