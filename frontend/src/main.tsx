import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { ApplicationShell } from "./layouts/application-shell";
import { OverviewPage } from "./pages/overview-page";

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(<StrictMode><QueryClientProvider client={queryClient}><ApplicationShell><OverviewPage /></ApplicationShell></QueryClientProvider></StrictMode>);
