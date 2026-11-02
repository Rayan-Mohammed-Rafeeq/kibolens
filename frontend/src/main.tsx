import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import { AuthProvider } from "./auth/auth-context";
import { ProtectedRoute } from "./auth/protected-route";
import { ApplicationShell } from "./layouts/application-shell";
import { ChatPage } from "./pages/chat-page";
import { KnowledgeBasePage } from "./pages/knowledge-base-page";
import { SettingsPage } from "./pages/settings-page";
import { LoginPage } from "./pages/login-page";
import { InfrastructurePage } from "./pages/infrastructure-page";
import { OverviewPage } from "./pages/overview-page";
import { IncidentsPage } from "./pages/incidents-page";
import { IncidentDetailPage } from "./pages/incident-detail-page";

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(<StrictMode><QueryClientProvider client={queryClient}><BrowserRouter><AuthProvider><Routes><Route path="/login" element={<LoginPage />} /><Route element={<ProtectedRoute />}><Route element={<ApplicationShell><OverviewPage /></ApplicationShell>} path="/" /><Route element={<ApplicationShell><ChatPage /></ApplicationShell>} path="/chat" /><Route element={<ApplicationShell><InfrastructurePage /></ApplicationShell>} path="/infrastructure" /><Route element={<ApplicationShell><IncidentsPage /></ApplicationShell>} path="/incidents" /><Route element={<ApplicationShell><IncidentDetailPage /></ApplicationShell>} path="/incidents/:id" /><Route element={<ApplicationShell><KnowledgeBasePage /></ApplicationShell>} path="/knowledge-base" /><Route element={<ApplicationShell><SettingsPage /></ApplicationShell>} path="/settings" /></Route></Routes></AuthProvider></BrowserRouter></QueryClientProvider></StrictMode>);
