import { api, qs } from "@/lib/api";
import type {
  ActivityEvent,
  Analysis,
  Analytics,
  Application,
  AppStatus,
  AuthResponse,
  DashboardSummary,
  Job,
  JobImport,
  JobInput,
  JobStatus,
  Length,
  Notification,
  Page,
  PortfolioMatch,
  PortfolioProject,
  Preferences,
  Profile,
  Proposal,
  ProposalListItem,
  ProposalVersion,
  Resume,
  Section,
  Tone,
  User,
} from "@/types/api";

type Params = Record<string, string | number | boolean | undefined | null>;

export const authApi = {
  session: () => api<AuthResponse>("/auth/session"),
  login: (email: string, password: string) =>
    api<AuthResponse>("/auth/login", { method: "POST", body: { email, password, client: "web" } }),
  register: (email: string, password: string, full_name?: string) =>
    api<AuthResponse>("/auth/register", { method: "POST", body: { email, password, full_name } }),
  logout: () => api("/auth/logout", { method: "POST" }),
  updateMe: (body: { full_name?: string; onboarding_completed?: boolean }) =>
    api<User>("/auth/me", { method: "PATCH", body }),
  forgot: (email: string) => api<{ message: string }>("/auth/forgot-password", { method: "POST", body: { email } }),
  reset: (token: string, new_password: string) =>
    api<{ message: string }>("/auth/reset-password", { method: "POST", body: { token, new_password } }),
  verifyEmail: (token: string) => api<{ message: string }>("/auth/verify-email", { method: "POST", body: { token } }),
  resendVerification: () => api<{ message: string }>("/auth/resend-verification", { method: "POST" }),
  changePassword: (current_password: string, new_password: string) =>
    api<{ message: string }>("/auth/change-password", { method: "POST", body: { current_password, new_password } }),
};

export const accountApi = {
  exportData: () => api<Record<string, unknown>>("/account/export"),
  remove: (password: string) => api<{ message: string }>("/account", { method: "DELETE", body: { password } }),
};

export const profileApi = {
  get: () => api<Profile>("/profile"),
  update: (body: Partial<Profile>) => api<Profile>("/profile", { method: "PUT", body }),
  clear: () => api("/profile", { method: "DELETE" }),
  preferences: () => api<Preferences>("/profile/preferences"),
  updatePreferences: (body: Preferences) => api<Preferences>("/profile/preferences", { method: "PUT", body }),
  uploadResume: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api<Resume>("/profile/resume", { method: "POST", body: fd });
  },
  resume: () => api<Resume>("/profile/resume"),
  applyResume: (body: Record<string, unknown>) => api<Profile>("/profile/resume/apply", { method: "POST", body }),
  deleteResume: () => api("/profile/resume", { method: "DELETE" }),
};

export const portfolioApi = {
  list: (p: Params = {}) => api<Page<PortfolioProject>>(`/portfolio${qs(p)}`),
  get: (id: string) => api<PortfolioProject>(`/portfolio/${id}`),
  create: (body: Record<string, unknown>) => api<PortfolioProject>("/portfolio", { method: "POST", body }),
  update: (id: string, body: Record<string, unknown>) => api<PortfolioProject>(`/portfolio/${id}`, { method: "PUT", body }),
  remove: (id: string) => api(`/portfolio/${id}`, { method: "DELETE" }),
  reindex: (force = false) =>
    api<{ indexed: number; skipped: number; failed: number }>(`/portfolio/reindex${qs({ force })}`, { method: "POST" }),
};

export const jobsApi = {
  list: (p: Params = {}) => api<Page<Job>>(`/jobs${qs(p)}`),
  get: (id: string) => api<Job>(`/jobs/${id}`),
  create: (body: JobInput, source: "manual" | "paste" = "manual") =>
    api<Job>(`/jobs${qs({ source })}`, { method: "POST", body }),
  update: (id: string, body: JobInput & { status: JobStatus }) => api<Job>(`/jobs/${id}`, { method: "PUT", body }),
  patch: (id: string, body: { status?: JobStatus; notes?: string }) => api<Job>(`/jobs/${id}`, { method: "PATCH", body }),
  remove: (id: string) => api(`/jobs/${id}`, { method: "DELETE" }),
  parseText: (text: string) => api<Partial<JobInput>>("/jobs/parse-text", { method: "POST", body: { text } }),
  importCsv: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api<JobImport>("/jobs/import/csv", { method: "POST", body: fd });
  },
  analyze: (id: string) => api<Analysis>(`/jobs/${id}/analyze`, { method: "POST" }),
  analysis: (id: string) => api<Analysis>(`/jobs/${id}/analysis`),
  analyses: (id: string) => api<Analysis[]>(`/jobs/${id}/analyses`),
  matchPortfolio: (id: string) => api<PortfolioMatch[]>(`/jobs/${id}/match-portfolio`, { method: "POST" }),
};

export interface GenerateOptions {
  job_id: string;
  tone?: Tone;
  length?: Length;
  emphasize_skills?: string[];
  project_ids?: string[];
  custom_opening?: string;
  exclude?: string[];
}

export const proposalsApi = {
  list: (p: Params = {}) => api<Page<ProposalListItem>>(`/proposals${qs(p)}`),
  get: (id: string) => api<Proposal>(`/proposals/${id}`),
  generate: (body: GenerateOptions) => api<Proposal>("/proposals/generate", { method: "POST", body }),
  update: (id: string, body: { content: string; title?: string; sections?: Partial<Record<Section, string>> }) =>
    api<Proposal>(`/proposals/${id}`, { method: "PUT", body }),
  remove: (id: string) => api(`/proposals/${id}`, { method: "DELETE" }),
  regenerate: (id: string, body: Omit<GenerateOptions, "job_id"> & { section?: Section }) =>
    api<Proposal>(`/proposals/${id}/regenerate`, { method: "POST", body }),
  snapshot: (id: string) => api<ProposalVersion>(`/proposals/${id}/versions`, { method: "POST" }),
  versions: (id: string) => api<ProposalVersion[]>(`/proposals/${id}/versions`),
  restore: (id: string, n: number) => api<Proposal>(`/proposals/${id}/versions/${n}/restore`, { method: "POST" }),
  exportFile: (id: string, format: "txt" | "md") => api<Response>(`/proposals/${id}/export${qs({ format })}`, { raw: true }),
};

export const applicationsApi = {
  list: (p: Params = {}) => api<Page<Application>>(`/applications${qs(p)}`),
  get: (id: string) => api<Application>(`/applications/${id}`),
  create: (body: { job_id: string; proposal_id?: string | null; status?: AppStatus; notes?: string }) =>
    api<Application>("/applications", { method: "POST", body }),
  update: (id: string, body: Record<string, unknown>) => api<Application>(`/applications/${id}`, { method: "PUT", body }),
  remove: (id: string) => api(`/applications/${id}`, { method: "DELETE" }),
};

export const dashboardApi = {
  summary: () => api<DashboardSummary>("/dashboard/summary"),
  analytics: (days = 30) => api<Analytics>(`/dashboard/analytics${qs({ days })}`),
  activity: () => api<ActivityEvent[]>("/dashboard/activity"),
};

export const notificationsApi = {
  list: (p: Params = {}) => api<Page<Notification> & { unread: number }>(`/notifications${qs(p)}`),
  read: (id: string) => api<Notification>(`/notifications/${id}/read`, { method: "POST" }),
  readAll: () => api("/notifications/read-all", { method: "POST" }),
};

export const adminApi = {
  users: (p: Params = {}) => api<Page<User & { last_login_at: string | null }>>(`/admin/users${qs(p)}`),
  updateUser: (id: string, body: { is_active?: boolean; role?: string }) =>
    api<User>(`/admin/users/${id}`, { method: "PATCH", body }),
  usage: (days = 30) => api<Record<string, unknown>>(`/admin/usage${qs({ days })}`),
  health: () => api<Record<string, unknown>>("/admin/health"),
  scoring: () => api<{ weights: Record<string, number>; thresholds: Record<string, number> }>("/admin/scoring-config"),
  updateScoring: (body: Record<string, number>) => api("/admin/scoring-config", { method: "PUT", body }),
  aiConfig: () => api<{ overrides: Record<string, unknown>; status: Record<string, unknown> }>("/admin/ai-config"),
  updateAiConfig: (body: Record<string, unknown>) => api("/admin/ai-config", { method: "PUT", body }),
  updateLimits: (body: { daily_ai_requests_per_user: number }) => api("/admin/usage-limits", { method: "PUT", body }),
  auditLogs: (p: Params = {}) => api<Page<Record<string, unknown>>>(`/admin/audit-logs${qs(p)}`),
};
