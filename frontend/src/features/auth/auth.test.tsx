import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ToastProvider } from "@/components/ui/overlays";
import { ProtectedRoute, AdminRoute } from "@/routes/guards";
import { mockFetch, renderApp, sessionNone, sessionOk, USER } from "@/test/utils";
import { AuthProvider } from "./AuthProvider";
import { LoginPage, RegisterPage } from "./AuthPages";

function renderGuarded(route: string, admin = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <ToastProvider>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<div>Login screen</div>} />
              <Route path="/unauthorized" element={<div>Unauthorized screen</div>} />
              <Route element={<ProtectedRoute />}>
                <Route path="/dashboard" element={<div>Secret dashboard</div>} />
                {admin && (
                  <Route element={<AdminRoute />}>
                    <Route path="/admin" element={<div>Admin area</div>} />
                  </Route>
                )}
              </Route>
            </Routes>
          </AuthProvider>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("authentication forms", () => {
  it("validates login fields before submitting", async () => {
    const { calls } = mockFetch({ ...sessionNone });
    renderApp(<LoginPage />, { route: "/login", path: "/login" });
    await userEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Email is required")).toBeInTheDocument();
    expect(screen.getByText("Password is required")).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("/auth/login"))).toBe(false);
  });

  it("shows the server's generic error on invalid credentials", async () => {
    mockFetch({
      ...sessionNone,
      "POST /api/v1/auth/login": () => ({ status: 401, body: { error: { code: "invalid_credentials", message: "Invalid email or password." } } }),
    });
    renderApp(<LoginPage />, { route: "/login", path: "/login" });
    await userEvent.type(await screen.findByLabelText("Email"), "alice@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Invalid email or password.")).toBeInTheDocument();
  });

  it("signs in and navigates away", async () => {
    const { calls } = mockFetch({ ...sessionNone, "POST /api/v1/auth/login": { user: USER, csrf_token: "t" } });
    renderApp(<LoginPage />, { route: "/login", path: "/login" });
    await userEvent.type(await screen.findByLabelText("Email"), "alice@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "CorrectHorse9Battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Other page")).toBeInTheDocument();
    const login = calls.find((c) => c.path.endsWith("/auth/login"));
    expect(login?.body).toEqual({ email: "alice@example.com", password: "CorrectHorse9Battery", client: "web" });
  });

  it("enforces password strength and confirmation on registration", async () => {
    mockFetch({ ...sessionNone });
    renderApp(<RegisterPage />, { route: "/register", path: "/register" });
    await userEvent.type(await screen.findByLabelText("Email"), "new@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "weakpass");
    await userEvent.type(screen.getByLabelText("Confirm password"), "different");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Use at least 10 characters")).toBeInTheDocument();
    expect(screen.getByText("Please confirm to continue")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Password"));
    await userEvent.type(screen.getByLabelText("Password"), "StrongPassw0rd");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Passwords do not match")).toBeInTheDocument();
  });
});

describe("protected routes", () => {
  it("redirects anonymous users to login", async () => {
    mockFetch({ ...sessionNone });
    renderGuarded("/dashboard");
    expect(await screen.findByText("Login screen")).toBeInTheDocument();
    expect(screen.queryByText("Secret dashboard")).not.toBeInTheDocument();
  });

  it("renders protected content for signed-in users", async () => {
    mockFetch({ ...sessionOk });
    renderGuarded("/dashboard");
    expect(await screen.findByText("Secret dashboard")).toBeInTheDocument();
  });

  it("blocks non-admins from admin routes", async () => {
    mockFetch({ ...sessionOk });
    renderGuarded("/admin", true);
    await waitFor(() => expect(screen.getByText("Unauthorized screen")).toBeInTheDocument());
  });
});
