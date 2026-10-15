/**
 * Minimal API client.
 * - Cookies (HttpOnly access/refresh) are sent automatically (credentials: "include").
 * - State-changing requests include the CSRF token (double-submit cookie pattern).
 * - A 401 triggers one silent refresh attempt, then the request is retried.
 */

export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let csrfToken: string | null = null;
let onUnauthorized: (() => void) | null = null;
let refreshing: Promise<boolean> | null = null;

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

function readCsrfCookie(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)bg_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

type Options = Omit<RequestInit, "body"> & { body?: unknown; raw?: boolean; skipRefresh?: boolean };

async function parseError(res: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `Request failed (${res.status})`;
  let details: unknown;
  try {
    const data = await res.json();
    if (data?.error) {
      code = data.error.code ?? code;
      message = data.error.message ?? message;
      details = data.error.details;
    }
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, code, message, details);
}

async function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          credentials: "include",
          headers: { "X-CSRF-Token": csrfToken ?? readCsrfCookie() ?? "" },
        });
        if (!res.ok) return false;
        const data = await res.json();
        setCsrfToken(data.csrf_token ?? null);
        return true;
      } catch {
        return false;
      } finally {
        setTimeout(() => (refreshing = null), 0);
      }
    })();
  }
  return refreshing;
}

export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const { body, raw, skipRefresh, headers, ...rest } = opts;
  const method = (rest.method ?? "GET").toUpperCase();
  const h = new Headers(headers);
  const isForm = body instanceof FormData;
  if (body !== undefined && !isForm) h.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const token = csrfToken ?? readCsrfCookie();
    if (token) h.set("X-CSRF-Token", token);
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...rest,
      method,
      headers: h,
      credentials: "include",
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network_error", "Could not reach the server. Check your connection and try again.");
  }
  if (res.status === 401 && !skipRefresh && !path.startsWith("/auth/login") && !path.startsWith("/auth/refresh")) {
    if (await refreshSession()) return api<T>(path, { ...opts, skipRefresh: true });
    onUnauthorized?.();
  }
  if (!res.ok) throw await parseError(res);
  if (raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  return (ct.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === "validation_error" && Array.isArray(err.details) && err.details.length) {
      const first = err.details[0] as { loc?: string[]; msg?: string };
      const field = first.loc?.filter((p) => p !== "body").join(".");
      return field ? `${field}: ${first.msg}` : (first.msg ?? err.message);
    }
    return err.message;
  }
  return err instanceof Error ? err.message : "Something went wrong.";
}

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}
