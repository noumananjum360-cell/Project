import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { ToastProvider } from "@/components/ui/overlays";
import { AuthProvider } from "@/features/auth/AuthProvider";
import type { User } from "@/types/api";

export const USER: User = {
  id: "u1",
  email: "alice@example.com",
  full_name: "Alice Example",
  role: "USER",
  is_active: true,
  email_verified_at: null,
  onboarding_completed: true,
  created_at: "2026-01-01T00:00:00Z",
};

type Handler = (url: URL, init: RequestInit) => { status?: number; body?: unknown } | undefined;

export interface FetchCall {
  method: string;
  path: string;
  body: unknown;
  headers: Headers;
}

/** Route-based fetch mock. Handlers receive the URL and return {status, body}. */
export function mockFetch(routes: Record<string, Handler | object>) {
  const calls: FetchCall[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init.method ?? "GET").toUpperCase();
    const body = typeof init.body === "string" ? JSON.parse(init.body) : init.body;
    calls.push({ method, path: url.pathname, body, headers: new Headers(init.headers) });
    const key = `${method} ${url.pathname}`;
    const route = routes[key] ?? routes[url.pathname];
    let res: { status?: number; body?: unknown } | undefined;
    if (typeof route === "function") res = (route as Handler)(url, init);
    else if (route !== undefined) res = { body: route };
    if (!res) res = { status: 404, body: { error: { code: "not_found", message: `No mock for ${key}` } } };
    return new Response(JSON.stringify(res.body ?? {}), {
      status: res.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls };
}

export function renderApp(ui: ReactElement, { route = "/", path = "/" }: { route?: string; path?: string } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <ToastProvider>
          <AuthProvider>
            <Routes>
              <Route path={path} element={ui} />
              <Route path="*" element={<div>Other page</div>} />
            </Routes>
          </AuthProvider>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export const sessionOk = { "GET /api/v1/auth/session": { user: USER, csrf_token: "csrf-123" } };
export const sessionNone = {
  "GET /api/v1/auth/session": () => ({ status: 401, body: { error: { code: "unauthorized", message: "Not authenticated." } } }),
  "POST /api/v1/auth/refresh": () => ({ status: 401, body: { error: { code: "refresh_invalid", message: "x" } } }),
};
