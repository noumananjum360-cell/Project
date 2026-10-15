import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { BackendClient, BackendError, type TokenStore } from "../src/services/api";
import { extractJob, parseBudget } from "../src/shared/extract";
import { isExtractedJob, isSupportedPage, parseMessage } from "../src/shared/messages";

const fixture = (name: string) => {
  const doc = document.implementation.createHTMLDocument("x");
  doc.documentElement.innerHTML = readFileSync(join(__dirname, "fixtures", name), "utf8");
  return doc;
};

describe("job extraction from representative fixtures", () => {
  it("extracts data-test based job pages", () => {
    const job = extractJob(fixture("job-page-data-test.html"), "https://www.upwork.com/jobs/~01abc123def4567890?referrer=x#top");
    expect(job).not.toBeNull();
    expect(job!.title).toBe("Senior React + FastAPI developer for analytics dashboard");
    expect(job!.description).toContain("internal analytics dashboard");
    expect(job!.description).toContain("FastAPI backend and PostgreSQL");
    expect(job!.job_type).toBe("hourly");
    expect(job!.budget_min).toBe("40.00");
    expect(job!.budget_max).toBe("70.00");
    expect(job!.experience_level).toBe("expert");
    expect(job!.required_skills).toEqual(["React", "TypeScript", "FastAPI", "PostgreSQL"]);
    expect(job!.client_info).toEqual({ payment_verified: true, rating: 4.8, country: "Canada" });
    expect(job!.url).toBe("https://www.upwork.com/jobs/~01abc123def4567890"); // query and fragment stripped
    expect(job!.proposals_info).toBe("10 to 15");
    expect(isExtractedJob(job)).toBe(true);
  });

  it("falls back to heading-based layouts", () => {
    const job = extractJob(fixture("job-page-fixed-heading.html"), "https://www.upwork.com/freelance-jobs/apply/logo_~01ff/");
    expect(job!.title).toBe("Logo and brand kit for a coffee shop");
    expect(job!.description).toMatch(/^Looking for a designer/);
    expect(job!.job_type).toBe("fixed");
    expect(job!.budget_max).toBe("300");
    expect(job!.experience_level).toBe("intermediate");
    expect(job!.required_skills).toContain("Logo Design");
    expect(job!.client_info?.payment_verified).toBe(false);
    expect(isExtractedJob(job)).toBe(true);
  });

  it("returns null when no job is present", () => {
    expect(extractJob(fixture("not-a-job-page.html"), "https://www.upwork.com/jobs/")).toBeNull();
  });

  it("parses budgets", () => {
    expect(parseBudget("$25 - $50 /hr Hourly")).toEqual({ job_type: "hourly", budget_min: "25", budget_max: "50" });
    expect(parseBudget("Fixed-price · Budget $1,500")).toEqual({ job_type: "fixed", budget_min: null, budget_max: "1500" });
    expect(parseBudget("No budget info")).toEqual({ job_type: "unknown", budget_min: null, budget_max: null });
  });
});

describe("message validation", () => {
  const job = extractJob(fixture("job-page-data-test.html"), "https://www.upwork.com/jobs/~01abc")!;

  it("accepts well-formed messages", () => {
    expect(parseMessage({ type: "JOB_EXTRACTED", action: "analyze", job })).not.toBeNull();
    expect(parseMessage({ type: "RUN_ON_TAB", tabId: 3, action: "write" })).toEqual({ type: "RUN_ON_TAB", tabId: 3, action: "write" });
    expect(parseMessage({ type: "SET_CONFIG", backendUrl: "https://api.example.com", dashboardUrl: "https://app.example.com" })).not.toBeNull();
  });

  it("rejects malformed or dangerous messages", () => {
    expect(parseMessage(null)).toBeNull();
    expect(parseMessage({ type: "DELETE_EVERYTHING" })).toBeNull();
    expect(parseMessage({ type: "RUN_ON_TAB", tabId: -1, action: "analyze" })).toBeNull();
    expect(parseMessage({ type: "RUN_ON_TAB", tabId: 1, action: "submit_proposal" })).toBeNull();
    expect(parseMessage({ type: "SET_CONFIG", backendUrl: "javascript:alert(1)", dashboardUrl: "https://x.com" })).toBeNull();
    expect(parseMessage({ type: "JOB_EXTRACTED", action: "analyze", job: { ...job, budget_max: "1e9; DROP" } })).toBeNull();
    expect(parseMessage({ type: "JOB_EXTRACTED", action: "analyze", job: { ...job, url: "http://evil.example" } })).toBeNull();
    expect(parseMessage({ type: "JOB_EXTRACTED", action: "analyze", job: { ...job, title: "x".repeat(301) } })).toBeNull();
    expect(parseMessage({ type: "LOGIN", email: "a@b.c", password: "x".repeat(500) })).toBeNull();
  });

  it("detects supported pages only", () => {
    expect(isSupportedPage("https://www.upwork.com/jobs/~01abc")).toBe(true);
    expect(isSupportedPage("https://www.upwork.com/freelance-jobs/apply/x_~01/")).toBe(true);
    expect(isSupportedPage("https://www.upwork.com/messages/rooms/1")).toBe(false);
    expect(isSupportedPage("https://evil.example/jobs/~01abc")).toBe(false);
    expect(isSupportedPage("http://www.upwork.com/jobs/~01")).toBe(false);
  });
});

function memoryTokens(initial = { access: null as string | null, refresh: null as string | null, email: null as string | null }): TokenStore & { v: typeof initial } {
  const store = { v: { ...initial } } as TokenStore & { v: typeof initial };
  store.get = async () => ({ ...store.v });
  store.set = async (n) => void (store.v = { ...n });
  return store;
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("backend client", () => {
  it("refreshes an expired access token once and retries", async () => {
    const tokens = memoryTokens({ access: "old", refresh: "r1", email: "a@b.c" });
    const calls: string[] = [];
    const fetchImpl = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(url)).pathname;
      const auth = new Headers(init?.headers).get("Authorization");
      calls.push(`${path} ${auth ?? ""}`);
      if (path.endsWith("/auth/me") && auth === "Bearer old") return json(401, { error: { code: "token_expired", message: "Session expired." } });
      if (path.endsWith("/auth/refresh")) return json(200, { user: { email: "a@b.c" }, tokens: { access_token: "new", refresh_token: "r2" } });
      if (path.endsWith("/auth/me")) return json(200, { email: "a@b.c" });
      return json(404, {});
    }) as unknown as typeof fetch;
    const c = new BackendClient("http://localhost:8000/", tokens, fetchImpl);
    expect(await c.me()).toEqual({ email: "a@b.c" });
    expect(tokens.v).toEqual({ access: "new", refresh: "r2", email: "a@b.c" });
    expect(calls).toEqual(["/api/v1/auth/me Bearer old", "/api/v1/auth/refresh ", "/api/v1/auth/me Bearer new"]);
  });

  it("signs out cleanly when refresh fails", async () => {
    const tokens = memoryTokens({ access: "old", refresh: "bad", email: "a@b.c" });
    const fetchImpl = (async () => json(401, { error: { code: "refresh_invalid", message: "x" } })) as unknown as typeof fetch;
    const c = new BackendClient("http://localhost:8000", tokens, fetchImpl);
    await expect(c.me()).rejects.toMatchObject({ status: 401, code: "signed_out" });
    expect(tokens.v.refresh).toBeNull();
  });

  it("reuses an existing job on duplicate import", async () => {
    const tokens = memoryTokens({ access: "a", refresh: "r", email: "x" });
    const fetchImpl = (async () =>
      json(409, { error: { code: "duplicate_job", message: "dup", details: { existing_job_id: "job-1" } } })) as unknown as typeof fetch;
    const c = new BackendClient("http://localhost:8000", tokens, fetchImpl);
    const job = extractJob(fixture("job-page-data-test.html"), "https://www.upwork.com/jobs/~01")!;
    expect(await c.saveJob(job)).toBe("job-1");
  });

  it("reports unreachable backends clearly", async () => {
    const c = new BackendClient("http://localhost:1", memoryTokens(), (async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch);
    await expect(c.health()).rejects.toBeInstanceOf(BackendError);
    await expect(c.health()).rejects.toMatchObject({ code: "network_error" });
  });
});
