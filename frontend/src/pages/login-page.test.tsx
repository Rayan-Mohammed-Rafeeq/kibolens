import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { LoginPage } from "./login-page";

const authServiceMocks = vi.hoisted(() => ({
  loginStage1: vi.fn(),
  verifyOtp: vi.fn(),
  resendOtp: vi.fn(),
}));

vi.mock("../auth/auth-context", () => ({ 
  useAuth: () => ({ user: null }) 
}));

vi.mock("../services/auth", () => ({
  loginStage1: authServiceMocks.loginStage1,
  verifyOtp: authServiceMocks.verifyOtp,
  resendOtp: authServiceMocks.resendOtp,
}));

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete (window as any).location;
    (window as any).location = { href: "" };
  });

  afterEach(() => {
    cleanup();
  });

  test("submits email and password then transitions to OTP stage", async () => {
    authServiceMocks.loginStage1.mockResolvedValue({
      requires_otp: true,
      masked_email: "ad***@example.com",
      resend_available_in: 60,
    });

    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    // Stage 1: Verify email and password form is rendered
    expect(screen.getByLabelText("Email")).toBeTruthy();
    expect(screen.getByLabelText("Password")).toBeTruthy();
    expect(screen.getByRole("button", { name: /send verification code/i })).toBeTruthy();

    // Fill in credentials
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "admin@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct-horse-battery-staple" } });

    // Submit credentials
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));

    // Verify loginStage1 was called with correct credentials
    await waitFor(() => {
      expect(authServiceMocks.loginStage1).toHaveBeenCalledWith("admin@example.com", "correct-horse-battery-staple");
    });

    // Stage 2: Verify OTP form is now rendered
    await waitFor(() => {
      expect(screen.getByLabelText("6-digit verification code")).toBeTruthy();
    });

    expect(screen.getByText(/ad\*\*\*@example\.com/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /verify and sign in/i })).toBeTruthy();
  });

  test("verifies OTP and completes authentication", async () => {
    authServiceMocks.loginStage1.mockResolvedValue({
      requires_otp: true,
      masked_email: "ad***@example.com",
      resend_available_in: 60,
    });

    authServiceMocks.verifyOtp.mockResolvedValue({
      id: "user-1",
      username: "admin",
      email: "admin@example.com",
      role: "administrator",
      created_at: "2026-10-31T00:00:00Z",
    });

    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    // Complete stage 1
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "admin@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));

    // Wait for OTP stage
    await waitFor(() => {
      expect(screen.getByLabelText("6-digit verification code")).toBeTruthy();
    });

    // Enter OTP
    const otpInput = screen.getByLabelText("6-digit verification code");
    fireEvent.change(otpInput, { target: { value: "123456" } });

    // Submit OTP
    fireEvent.click(screen.getByRole("button", { name: /verify and sign in/i }));

    // Verify verifyOtp was called
    await waitFor(() => {
      expect(authServiceMocks.verifyOtp).toHaveBeenCalledWith("admin@example.com", "123456");
    });

    // Verify redirect happens
    await waitFor(() => {
      expect(window.location.href).toBe("/chat");
    });
  });

  test("displays error when invalid OTP is submitted", async () => {
    authServiceMocks.loginStage1.mockResolvedValue({
      requires_otp: true,
      masked_email: "ad***@example.com",
      resend_available_in: 60,
    });

    authServiceMocks.verifyOtp.mockRejectedValue(new Error("Invalid or expired verification code"));

    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    // Complete stage 1
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "admin@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));

    // Wait for OTP stage
    await waitFor(() => {
      expect(screen.getByLabelText("6-digit verification code")).toBeTruthy();
    });

    // Enter wrong OTP
    fireEvent.change(screen.getByLabelText("6-digit verification code"), { target: { value: "999999" } });
    fireEvent.click(screen.getByRole("button", { name: /verify and sign in/i }));

    // Verify error is displayed
    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert.textContent).toBe("Invalid or expired verification code");
    });
  });

  test("displays error when credentials are invalid", async () => {
    authServiceMocks.loginStage1.mockRejectedValue(new Error("Invalid email or password"));

    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "wrong@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrongpassword" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));

    // Verify error is displayed
    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert.textContent).toBe("Invalid email or password");
    });

    // Verify we're still on credentials stage
    expect(screen.getByLabelText("Email")).toBeTruthy();
    expect(screen.queryByLabelText("6-digit verification code")).toBeFalsy();
  });

  test("allows resending OTP after cooldown", async () => {
    vi.useFakeTimers();

    authServiceMocks.loginStage1.mockResolvedValue({
      requires_otp: true,
      masked_email: "ad***@example.com",
      resend_available_in: 5,
    });

    authServiceMocks.resendOtp.mockResolvedValue({
      success: true,
      masked_email: "ad***@example.com",
      resend_available_in: 60,
    });

    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    // Complete stage 1
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "admin@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));

    // Wait for OTP stage
    await vi.waitFor(() => {
      expect(screen.getByLabelText("6-digit verification code")).toBeTruthy();
    }, { timeout: 1000 });

    // Verify resend button shows cooldown
    expect(screen.getByRole("button", { name: /resend in 5s/i })).toBeTruthy();

    // Fast-forward past cooldown
    vi.advanceTimersByTime(5000);

    // Wait for button text to change
    await vi.waitFor(() => {
      expect(screen.queryByRole("button", { name: /resend code/i })).toBeTruthy();
    }, { timeout: 1000 });

    // Click resend
    fireEvent.click(screen.getByRole("button", { name: /resend code/i }));

    // Verify resendOtp was called
    await vi.waitFor(() => {
      expect(authServiceMocks.resendOtp).toHaveBeenCalledWith("admin@example.com");
    }, { timeout: 1000 });

    vi.useRealTimers();
  });

  test("allows navigating back to credentials stage", async () => {
    authServiceMocks.loginStage1.mockResolvedValue({
      requires_otp: true,
      masked_email: "ad***@example.com",
      resend_available_in: 60,
    });

    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    // Complete stage 1
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "admin@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));

    // Wait for OTP stage
    await waitFor(() => {
      expect(screen.getByLabelText("6-digit verification code")).toBeTruthy();
    });

    // Click back button
    const backButton = screen.getByRole("button", { name: /back/i });
    fireEvent.click(backButton);

    // Verify we're back on credentials stage - just check the button text changed
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /send verification code/i })).toBeTruthy();
    });
  });

  test("only allows numeric input for OTP", async () => {
    authServiceMocks.loginStage1.mockResolvedValue({
      requires_otp: true,
      masked_email: "ad***@example.com",
      resend_available_in: 60,
    });

    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    // Complete stage 1
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "admin@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /send verification code/i }));

    // Wait for OTP stage
    await waitFor(() => {
      expect(screen.getByLabelText("6-digit verification code")).toBeTruthy();
    });

    // Try entering non-numeric characters
    const otpInput = screen.getByLabelText("6-digit verification code") as HTMLInputElement;
    fireEvent.change(otpInput, { target: { value: "abc123xyz" } });

    // Verify only numeric characters are accepted (filter happens on change handler)
    expect(otpInput.value).toBe("123");
  });
});
