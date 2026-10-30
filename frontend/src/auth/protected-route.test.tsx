import { render, screen } from "@testing-library/react";
import { Route, Routes, MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";
import { ProtectedRoute } from "./protected-route";

const mocks = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock("./auth-context", () => ({ useAuth: mocks.useAuth }));

function renderRoutes() {
  return render(<MemoryRouter initialEntries={["/"]}><Routes><Route path="/login" element={<p>Login page</p>} /><Route element={<ProtectedRoute />}><Route path="/" element={<p>Private application</p>} /></Route></Routes></MemoryRouter>);
}

describe("ProtectedRoute", () => {
  test("redirects an unauthenticated visitor to login", () => {
    mocks.useAuth.mockReturnValue({ user: null, loading: false });
    renderRoutes();
    expect(screen.getByText("Login page")).toBeTruthy();
  });

  test("renders private content for an authenticated user", () => {
    mocks.useAuth.mockReturnValue({ user: { username: "admin" }, loading: false });
    renderRoutes();
    expect(screen.getByText("Private application")).toBeTruthy();
  });
});
