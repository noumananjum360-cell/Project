/**
 * BidGenie backend client used by the background service worker.
 *
 * - The OpenAI key never reaches the extension: all AI work happens on the backend.
 * - The extension signs in with the "extension" client type and receives a
 *   short-lived access token plus a rotating refresh token (stored in
 *   chrome.storage.local, never in page context).
 */
import type { AnalysisSummary, ExtractedJob, ProposalSummary } from "../shared/types";

export interface TokenStore {
  get(): Promise<{ access: string | null; refresh: string | null; email: string | null }>;
  set(v: { access: string | null; refresh: string | null; email: string | null }): Promise<void>;
}

export class BackendError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

export class BackendClient {
  constructor(
    private baseUrl: string,
    private tokens: TokenStore,
    private fetchImpl: typeof fetch = (...a) => fetch(...a),
  ) {}

  private url(path: string) {
    return `${this.baseUrl.replace(/\/+$/, "")}/api/v1${path}`;
  }

  private async raw(path: string, init: RequestInit = {}, access?: string | null): Promise<Response> {
    const headers = new Headers(init.headers);
    if (init.body) headers.set("Content-Type", "application/json");
    if (access) headers.set("Authorization", `Bearer ${access}`);
    try {
      return await this.fetchImpl(this.url(path), { ...init, headers, credentials: "omit" });
    } catch {
      throw new BackendError(0, "network_error", `Cannot reach the BidGenie backend at ${this.baseUrl}.`);
    }
  }

  private static async error(res: Response): Promise<BackendError> {
    try {
      const body = await res.json();
      if (body?.error) return new BackendError(res.status, body.error.code, body.error.message, body.error.details);
    } catch {
      /* non-JSON */
    }
    return new BackendError(res.status, "http_error", `Request failed (HTTP ${res.status}).`);
  }

  private async refresh(): Promise<string | null> {
    const t = await this.tokens.get();
    if (!t.refresh) return null;
    const res = await this.raw("/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token: t.refresh }) });
    if (!res.ok) {
      await this.tokens.set({ access: null, refresh: null, email: t.email });
      return null;
    }
    const data = await res.json();
    await this.tokens.set({ access: data.tokens.access_token, refresh: data.tokens.refresh_token, email: data.user.email });
    return data.tokens.access_token as string;
  }

  /** Authenticated request with one transparent refresh on 401. */
  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    let { access } = await this.tokens.get();
    if (!access) access = await this.refresh();
    if (!access) throw new BackendError(401, "signed_out", "Please sign in to BidGenie from the extension popup.");
    let res = await this.raw(path, init, access);
    if (res.status === 401) {
      const renewed = await this.refresh();
      if (!renewed) throw new BackendError(401, "signed_out", "Your session expired. Please sign in again.");
      res = await this.raw(path, init, renewed);
    }
    if (!res.ok) throw await BackendClient.error(res);
    return (await res.json()) as T;
  }

  async health(): Promise<{ ai_configured: boolean; ai_simulated: boolean }> {
    const res = await this.raw("/health/ready");
    if (!res.ok) throw await BackendClient.error(res);
    return res.json();
  }

  async login(email: string, password: string): Promise<string> {
    const res = await this.raw("/auth/login", { method: "POST", body: JSON.stringify({ email, password, client: "extension" }) });
    if (!res.ok) throw await BackendClient.error(res);
    const data = await res.json();
    await this.tokens.set({ access: data.tokens.access_token, refresh: data.tokens.refresh_token, email: data.user.email });
    return data.user.email as string;
  }

  async logout(): Promise<void> {
    const t = await this.tokens.get();
    try {
      if (t.refresh) await this.raw("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: t.refresh }) });
    } finally {
      await this.tokens.set({ access: null, refresh: null, email: null });
    }
  }

  async me(): Promise<{ email: string }> {
    return this.request("/auth/me");
  }

  /** Save the job; if it already exists, reuse the existing record. */
  async saveJob(job: ExtractedJob): Promise<string> {
    try {
      const created = await this.request<{ id: string }>("/jobs/from-extension", { method: "POST", body: JSON.stringify(job) });
      return created.id;
    } catch (e) {
      const existing = (e as BackendError).details as { existing_job_id?: string } | undefined;
      if (e instanceof BackendError && e.code === "duplicate_job" && existing?.existing_job_id) return existing.existing_job_id;
      throw e;
    }
  }

  async analyze(jobId: string): Promise<AnalysisSummary> {
    const a = await this.request<{
      fit_score: number;
      recommendation: string;
      score_confidence: number;
      is_simulated: boolean;
      result: {
        matched_skills: string[];
        missing_skills: string[];
        red_flags: { flag: string; evidence: string; severity: string }[];
        relevant_portfolio_projects: { title: string; similarity: number; evidence: string }[];
        explanation: string;
      };
    }>(`/jobs/${jobId}/analyze`, { method: "POST" });
    return {
      job_id: jobId,
      fit_score: a.fit_score,
      recommendation: a.recommendation,
      score_confidence: a.score_confidence,
      matched_skills: a.result.matched_skills,
      missing_skills: a.result.missing_skills,
      red_flags: a.result.red_flags,
      portfolio: a.result.relevant_portfolio_projects.map((p) => ({ title: p.title, similarity: p.similarity, evidence: p.evidence })),
      explanation: a.result.explanation,
      is_simulated: a.is_simulated,
    };
  }

  async writeProposal(jobId: string): Promise<ProposalSummary> {
    const p = await this.request<{ id: string; content: string; warnings: string[]; is_simulated: boolean }>("/proposals/generate", {
      method: "POST",
      body: JSON.stringify({ job_id: jobId }),
    });
    return { id: p.id, content: p.content, warnings: p.warnings, is_simulated: p.is_simulated };
  }
}
