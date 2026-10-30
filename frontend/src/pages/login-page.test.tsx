import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";
import { LoginPage } from "./login-page";

const mocks = vi.hoisted(() => ({ login: vi.fn() }));
vi.mock("../auth/auth-context", () => ({ useAuth: () => ({ user: null, login: mocks.login }) }));

describe("LoginPage", () => {
  test("submits username and password through the authentication context", async () => {
    mocks.login.mockResolvedValue(undefined);
    render(<MemoryRouter><LoginPage /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct-horse-battery-staple" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await vi.waitFor(() => expect(mocks.login).toHaveBeenCalledWith("admin", "correct-horse-battery-staple"));
  });
});
