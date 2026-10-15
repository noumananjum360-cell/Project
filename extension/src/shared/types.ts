/** Job details extracted from the visible page (subset of the backend JobCreate schema). */
export interface ExtractedJob {
  title: string;
  description: string;
  url: string | null;
  budget_min: string | null;
  budget_max: string | null;
  currency: string;
  job_type: "hourly" | "fixed" | "unknown";
  required_skills: string[];
  experience_level: "entry" | "intermediate" | "expert" | "unknown";
  client_info: { payment_verified?: boolean | null; rating?: number | null; country?: string | null } | null;
  proposals_info: string | null;
}

export interface AnalysisSummary {
  job_id: string;
  fit_score: number;
  recommendation: string;
  score_confidence: number;
  matched_skills: string[];
  missing_skills: string[];
  red_flags: { flag: string; evidence: string; severity: string }[];
  portfolio: { title: string; similarity: number; evidence: string }[];
  explanation: string;
  is_simulated: boolean;
}

export interface ProposalSummary {
  id: string;
  content: string;
  warnings: string[];
  is_simulated: boolean;
}

export type TabStatus = "idle" | "extracting" | "saving" | "analyzing" | "writing" | "done" | "error";

export interface TabState {
  status: TabStatus;
  job: ExtractedJob | null;
  jobId: string | null;
  analysis: AnalysisSummary | null;
  proposal: ProposalSummary | null;
  error: string | null;
  updatedAt: number;
}

export interface ExtensionConfig {
  backendUrl: string;
  dashboardUrl: string;
}

export interface ConnectionStatus {
  backendReachable: boolean;
  signedIn: boolean;
  email: string | null;
  aiConfigured: boolean | null;
  aiSimulated: boolean | null;
  error: string | null;
}

export const DEFAULT_CONFIG: ExtensionConfig = {
  backendUrl: "http://localhost:8000",
  dashboardUrl: "http://localhost:5173",
};

export function emptyTabState(): TabState {
  return { status: "idle", job: null, jobId: null, analysis: null, proposal: null, error: null, updatedAt: Date.now() };
}
