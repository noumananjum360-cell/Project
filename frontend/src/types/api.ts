export type Role = "USER" | "ADMIN";

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  email_verified_at: string | null;
  onboarding_completed: boolean;
  created_at: string;
}

export interface AuthResponse {
  user: User;
  csrf_token: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export type Tone = "professional" | "friendly" | "confident" | "concise" | "technical";
export type Length = "short" | "standard" | "detailed";

export interface Profile {
  full_name: string | null;
  headline: string | null;
  overview: string | null;
  primary_skills: string[];
  additional_skills: string[];
  years_experience: number | null;
  hourly_rate: string | null;
  currency: string;
  preferred_categories: string[];
  preferred_project_types: string[];
  min_budget: string | null;
  preferred_client_traits: string[];
  proposal_tone: Tone;
  proposal_length: Length;
  languages: string[];
  timezone: string | null;
  availability: string | null;
  profile_version: number;
  is_demo: boolean;
  updated_at: string;
}

export interface Preferences {
  fit_score_threshold: number;
  auto_analyze_on_import: boolean;
  notify_high_fit_jobs: boolean;
  notify_follow_ups: boolean;
}

export interface ResumeExtraction {
  full_name?: string | null;
  headline?: string | null;
  overview?: string | null;
  skills: string[];
  years_experience?: number | null;
  languages: string[];
  experience: { title: string; organization?: string | null; period?: string | null; summary?: string | null }[];
  education: string[];
  certifications: string[];
  keyword_skills: string[];
  verification_note: string;
  notice?: string;
}

export interface Resume {
  id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  status: "uploaded" | "parsed" | "applied" | "failed";
  error: string | null;
  extracted_data: ResumeExtraction | null;
  extraction_method: "ai" | "keyword" | null;
  is_simulated: boolean;
  file_retained: boolean;
  applied_at: string | null;
  created_at: string;
}

export interface PortfolioProject {
  id: string;
  title: string;
  description: string;
  skills: string[];
  category: string | null;
  role: string | null;
  achievements: string | null;
  url: string | null;
  image_url: string | null;
  start_date: string | null;
  end_date: string | null;
  duration_text: string | null;
  is_demo: boolean;
  embedding_status: "pending" | "ready" | "failed";
  embedding_error: string | null;
  embedded_at: string | null;
  created_at: string;
  updated_at: string;
}

export type JobType = "hourly" | "fixed" | "unknown";
export type ExperienceLevel = "entry" | "intermediate" | "expert" | "unknown";
export type JobStatus = "new" | "saved" | "shortlisted" | "applied" | "skipped" | "archived";

export interface ClientInfo {
  country?: string | null;
  payment_verified?: boolean | null;
  rating?: number | null;
  reviews_count?: number | null;
  total_spent?: string | null;
  hire_rate?: string | null;
  jobs_posted?: number | null;
}

export interface Job {
  id: string;
  title: string;
  description: string;
  budget_min: string | null;
  budget_max: string | null;
  currency: string;
  job_type: JobType;
  required_skills: string[];
  experience_level: ExperienceLevel;
  client_info: ClientInfo;
  proposals_info: string | null;
  posted_at: string | null;
  url: string | null;
  source: string;
  is_demo: boolean;
  status: JobStatus;
  notes: string | null;
  latest_fit_score: number | null;
  latest_recommendation: Recommendation | null;
  analyzed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobInput {
  title: string;
  description: string;
  budget_min?: string | null;
  budget_max?: string | null;
  currency?: string;
  job_type?: JobType;
  required_skills?: string[];
  experience_level?: ExperienceLevel;
  client_info?: ClientInfo | null;
  proposals_info?: string | null;
  posted_at?: string | null;
  url?: string | null;
  notes?: string | null;
}

export interface JobImport {
  id: string;
  source: string;
  filename: string | null;
  total_rows: number;
  created_count: number;
  duplicate_count: number;
  error_count: number;
  errors: { line: number; error: string }[];
  created_at: string;
}

export type Recommendation = "Strong Match" | "Possible Match" | "Weak Match" | "Insufficient Information";

export interface PortfolioMatch {
  project_id: string;
  title: string;
  similarity: number;
  shared_skills: string[];
  evidence: string;
  url: string | null;
  is_demo: boolean;
}

export interface RedFlag {
  flag: string;
  evidence: string;
  severity: "low" | "medium" | "high";
  category: string;
  source: "rules" | "ai";
}

export interface BreakdownItem {
  factor: string;
  label: string;
  weight: number;
  effective_weight: number;
  score: number | null;
  points: number | null;
  status: "known" | "unknown";
  detail: string;
}

export interface AnalysisResult {
  fit_score: number;
  score_confidence: number;
  recommendation: Recommendation;
  matched_skills: string[];
  partially_matched_skills: { skill: string; via: string }[];
  missing_skills: string[];
  required_skills_inferred: boolean;
  relevant_experience: string[];
  relevant_portfolio_projects: PortfolioMatch[];
  budget_compatibility: { status: string; detail: string };
  feasibility_assessment: string;
  red_flags: RedFlag[];
  positive_signals: string[];
  missing_information: string[];
  score_breakdown: BreakdownItem[];
  explanation: string;
  suggested_next_steps: string[];
  narrative_source: "ai" | "deterministic_fallback";
  ai_generated_fields: string[];
  is_simulated: boolean;
}

export interface Analysis {
  id: string;
  job_id: string;
  fit_score: number;
  score_confidence: number;
  recommendation: Recommendation;
  result: AnalysisResult;
  weights: Record<string, number>;
  scoring_version: string;
  provider: string;
  model: string | null;
  embedding_model: string | null;
  profile_version: number | null;
  is_simulated: boolean;
  created_at: string;
  profile_changed_since: boolean;
}

export type Section = "hook" | "solution" | "proof" | "call_to_action";

export interface Proposal {
  id: string;
  job_id: string;
  title: string;
  content: string;
  sections: Partial<Record<Section, string>>;
  tone: Tone;
  length: Length;
  options: Record<string, unknown>;
  current_version_number: number;
  warnings: string[];
  is_simulated: boolean;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProposalListItem {
  id: string;
  job_id: string;
  title: string;
  tone: Tone;
  length: Length;
  current_version_number: number;
  is_simulated: boolean;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
  job_title: string | null;
  application_status: AppStatus | null;
}

export interface ProposalVersion {
  id: string;
  version_number: number;
  content: string;
  sections: Partial<Record<Section, string>>;
  source: "generated" | "regenerated" | "section_regenerated" | "manual";
  provider: string | null;
  model: string | null;
  prompt_version: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  estimated_cost: string | null;
  used_project_ids: string[];
  warnings: string[];
  is_simulated: boolean;
  created_at: string;
}

export type AppStatus = "draft" | "ready" | "sent" | "interview" | "hired" | "declined" | "archived";

export interface Application {
  id: string;
  job_id: string;
  proposal_id: string | null;
  proposal_version_number: number | null;
  status: AppStatus;
  submitted_at: string | null;
  interview_at: string | null;
  contract_value: string | null;
  contract_currency: string;
  follow_up_at: string | null;
  notes: string | null;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
  job_title: string | null;
  job_fit_score: number | null;
  history: { id: string; from_status: string | null; to_status: string; note: string | null; created_at: string }[];
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string | null;
  link: string | null;
  read_at: string | null;
  created_at: string;
}

export interface AIStatus {
  provider: string;
  configured: boolean;
  simulated: boolean;
  demo_mode: boolean;
  chat_model: string;
  embedding_model: string;
}

export interface DashboardSummary {
  total_jobs: number;
  jobs_analyzed: number;
  strong_matches: number;
  proposals_generated: number;
  proposals_sent: number;
  interviews: number;
  hires: number;
  average_fit_score: number | null;
  ai_requests: number;
  ai_input_tokens: number;
  ai_output_tokens: number;
  ai_estimated_cost: number | null;
  ai_cost_complete: boolean;
  ai_status: AIStatus;
  notes: string;
}

export interface Analytics {
  days: number;
  timeline: { date: string; jobs_imported: number; jobs_analyzed: number; proposals: number }[];
  fit_score_distribution: { range: string; count: number }[];
  status_breakdown: { status: AppStatus; count: number }[];
  outcomes: { outcome: string; count: number }[];
  top_matched_skills: { skill: string; count: number }[];
  top_missing_skills: { skill: string; count: number }[];
}

export interface ActivityEvent {
  type: "job_imported" | "job_analyzed" | "proposal_generated" | "status_changed";
  at: string;
  title: string;
  link: string;
  is_demo: boolean;
}
