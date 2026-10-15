import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnalysisView } from "@/features/job-analysis/AnalysisView";
import JobFeedPage from "@/features/jobs/JobFeedPage";
import { ProfileForm } from "@/features/profile/ProfileForm";
import ProposalEditorPage from "@/features/proposals/ProposalEditorPage";
import TrackerPage from "@/features/tracking/TrackerPage";
import AppLayout from "@/layouts/AppLayout";
import { mockFetch, renderApp, sessionOk } from "@/test/utils";
import type { Analysis, Application, Job, Profile, Proposal } from "@/types/api";

const PROFILE: Profile = {
  full_name: "Alice",
  headline: "",
  overview: "",
  primary_skills: ["React"],
  additional_skills: [],
  years_experience: 5,
  hourly_rate: "60.00",
  currency: "USD",
  preferred_categories: [],
  preferred_project_types: [],
  min_budget: null,
  preferred_client_traits: [],
  proposal_tone: "professional",
  proposal_length: "standard",
  languages: [],
  timezone: null,
  availability: null,
  profile_version: 1,
  is_demo: false,
  updated_at: "2026-01-01T00:00:00Z",
};

const JOB: Job = {
  id: "j1",
  title: "React dashboard developer",
  description: "Build a dashboard with React and TypeScript.",
  budget_min: "40",
  budget_max: "70",
  currency: "USD",
  job_type: "hourly",
  required_skills: ["React", "TypeScript"],
  experience_level: "expert",
  client_info: {},
  proposals_info: null,
  posted_at: null,
  url: null,
  source: "manual",
  is_demo: false,
  status: "new",
  notes: null,
  latest_fit_score: 82,
  latest_recommendation: "Strong Match",
  analyzed_at: "2026-01-02T00:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const page = <T,>(items: T[]) => ({ items, total: items.length, page: 1, page_size: 20, pages: 1 });

afterEach(() => {
  vi.useRealTimers();
});

describe("profile editing", () => {
  it("validates and saves profile fields", async () => {
    const { calls } = mockFetch({ ...sessionOk, "PUT /api/v1/profile": (_u, init) => ({ body: { ...PROFILE, ...JSON.parse(String(init.body)), profile_version: 2 } }) });
    renderApp(<ProfileForm profile={PROFILE} />);
    const rate = await screen.findByLabelText("Hourly rate");
    await userEvent.clear(rate);
    await userEvent.type(rate, "-5");
    await userEvent.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText(/Enter a positive amount/)).toBeInTheDocument();

    await userEvent.clear(rate);
    await userEvent.type(rate, "75.50");
    await userEvent.type(screen.getByLabelText("Primary skills"), "Python{enter}");
    await userEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.body).toMatchObject({ hourly_rate: "75.50", primary_skills: ["React", "Python"], years_experience: 5 });
    expect(put.headers.get("X-CSRF-Token")).toBe("csrf-123");
    expect(await screen.findByText("Profile saved.")).toBeInTheDocument();
  });
});

describe("job feed", () => {
  it("shows a loading state, then jobs", async () => {
    mockFetch({ ...sessionOk, "GET /api/v1/jobs": page([JOB]) });
    renderApp(<JobFeedPage />);
    expect(await screen.findByText("React dashboard developer")).toBeInTheDocument();
    expect(screen.getByText("Fit 82")).toBeInTheDocument();
    expect(screen.getByText("Strong Match")).toBeInTheDocument();
  });

  it("shows an error state with retry", async () => {
    let fail = true;
    mockFetch({
      ...sessionOk,
      "GET /api/v1/jobs": () => (fail ? { status: 400, body: { error: { code: "x", message: "Could not load jobs." } } } : { body: page([JOB]) }),
    });
    renderApp(<JobFeedPage />);
    expect(await screen.findByText("Could not load jobs.")).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("React dashboard developer")).toBeInTheDocument();
  });

  it("imports a pasted job after review", async () => {
    const { calls } = mockFetch({
      ...sessionOk,
      "GET /api/v1/jobs": page([]),
      "POST /api/v1/jobs/parse-text": { title: "Need a Python dev", description: "Build a Python API with FastAPI for our startup.", job_type: "fixed", budget_max: "500", required_skills: ["python"], experience_level: "unknown" },
      "POST /api/v1/jobs": { ...JOB, id: "new-job" },
    });
    renderApp(<JobFeedPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Add your first job" }));
    await userEvent.click(screen.getByRole("tab", { name: "Paste job post" }));
    await userEvent.type(screen.getByLabelText("Job post text"), "Need a Python dev\nBuild a Python API with FastAPI for our startup.");
    await userEvent.click(screen.getByRole("button", { name: "Extract fields for review" }));
    expect(await screen.findByDisplayValue("Need a Python dev")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save job" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/v1/jobs")).toBe(true));
    const post = calls.find((c) => c.method === "POST" && c.path === "/api/v1/jobs")!;
    expect(post.body).toMatchObject({ title: "Need a Python dev", job_type: "fixed", budget_max: "500", required_skills: ["python"] });
    expect(await screen.findByText("Other page")).toBeInTheDocument();
  });
});

describe("analysis display", () => {
  it("renders score, skills, unknown factors, portfolio evidence and warning signs", () => {
    const analysis: Analysis = {
      id: "a1",
      job_id: "j1",
      fit_score: 68,
      score_confidence: 0.85,
      recommendation: "Possible Match",
      weights: {},
      scoring_version: "1.0.0",
      provider: "mock",
      model: "bidgenie-simulated-v1",
      embedding_model: "x",
      profile_version: 1,
      is_simulated: true,
      created_at: "2026-01-02T00:00:00Z",
      profile_changed_since: true,
      result: {
        fit_score: 68,
        score_confidence: 0.85,
        recommendation: "Possible Match",
        matched_skills: ["react"],
        partially_matched_skills: [{ skill: "next.js", via: "react" }],
        missing_skills: ["graphql"],
        required_skills_inferred: false,
        relevant_experience: [],
        relevant_portfolio_projects: [{ project_id: "p1", title: "Inventory dashboard", similarity: 0.61, shared_skills: ["react"], evidence: "Built a React dashboard", url: null, is_demo: false }],
        budget_compatibility: { status: "compatible", detail: "Budget ok." },
        feasibility_assessment: "Feasible.",
        red_flags: [{ flag: "Potential warning sign: asks to move communication off-platform", evidence: "“…Telegram…”", severity: "high", category: "risk", source: "rules" }],
        positive_signals: ["Matches required skills: react"],
        missing_information: ["The job does not state an experience level."],
        score_breakdown: [
          { factor: "skills", label: "Required-skill match", weight: 30, effective_weight: 35.3, score: 0.6, points: 21.2, status: "known", detail: "1 matched" },
          { factor: "experience", label: "Experience & complexity match", weight: 15, effective_weight: 0, score: null, points: null, status: "unknown", detail: "No level" },
        ],
        explanation: "Explained.",
        suggested_next_steps: ["Clarify scope."],
        narrative_source: "ai",
        ai_generated_fields: ["explanation"],
        is_simulated: true,
      },
    };
    renderApp(<AnalysisView analysis={analysis} />);
    expect(screen.getByRole("img", { name: "Fit Score: 68 out of 100" })).toBeInTheDocument();
    expect(screen.getByText("Possible Match")).toBeInTheDocument();
    expect(screen.getByText("Simulated AI")).toBeInTheDocument();
    expect(screen.getByText("graphql")).toBeInTheDocument();
    expect(screen.getByText("next.js (via react)")).toBeInTheDocument();
    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.getByText("Similarity 61%")).toBeInTheDocument();
    expect(screen.getByText(/asks to move communication off-platform/)).toBeInTheDocument();
    expect(screen.getByText(/profile or portfolio changed/)).toBeInTheDocument();
  });
});

describe("proposal editing", () => {
  const PROPOSAL: Proposal = {
    id: "p1",
    job_id: "j1",
    title: "Proposal: React dashboard developer",
    content: "Hook text.\n\nSolution text.",
    sections: { hook: "Hook text.", solution: "Solution text." },
    tone: "professional",
    length: "standard",
    options: {},
    current_version_number: 1,
    warnings: ["Review these figures — they do not appear in your profile: 300%"],
    is_simulated: false,
    is_demo: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };

  it("autosaves edits with debounce and shows warnings", async () => {
    let saved = "";
    const { calls } = mockFetch({
      ...sessionOk,
      "GET /api/v1/proposals/p1": PROPOSAL,
      "PUT /api/v1/proposals/p1": (_u, init) => {
        saved = JSON.parse(String(init.body)).content;
        return { body: { ...PROPOSAL, content: saved, updated_at: "2026-01-01T00:00:05Z" } };
      },
    });
    renderApp(<ProposalEditorPage />, { route: "/proposals/p1", path: "/proposals/:id" });
    const editor = await screen.findByLabelText("Proposal text");
    expect(screen.getByText(/300%/)).toBeInTheDocument();
    fireEvent.change(editor, { target: { value: "Edited proposal body" } });
    expect(screen.getByText("Unsaved changes…")).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "PUT")).toHaveLength(0);
    await waitFor(() => expect(saved).toBe("Edited proposal body"), { timeout: 3000 });
    expect(await screen.findByText("All changes saved")).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "PUT")).toHaveLength(1);
  });

  it("copies the proposal to the clipboard", async () => {
    mockFetch({ ...sessionOk, "GET /api/v1/proposals/p1": PROPOSAL });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderApp(<ProposalEditorPage />, { route: "/proposals/p1", path: "/proposals/:id" });
    await screen.findByLabelText("Proposal text");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    });
    expect(writeText).toHaveBeenCalledWith(PROPOSAL.content);
  });
});

describe("application tracker", () => {
  it("updates a status from the board", async () => {
    const app: Application = {
      id: "a1",
      job_id: "j1",
      proposal_id: null,
      proposal_version_number: null,
      status: "draft",
      submitted_at: null,
      interview_at: null,
      contract_value: null,
      contract_currency: "USD",
      follow_up_at: null,
      notes: null,
      is_demo: false,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      job_title: "React dashboard developer",
      job_fit_score: 82,
      history: [],
    };
    const { calls } = mockFetch({
      ...sessionOk,
      "GET /api/v1/applications": page([app]),
      "PUT /api/v1/applications/a1": (_u, init) => ({ body: { ...app, ...JSON.parse(String(init.body)) } }),
    });
    renderApp(<TrackerPage />);
    const select = await screen.findByLabelText("Move React dashboard developer to status");
    await userEvent.selectOptions(select, "sent");
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(calls.find((c) => c.method === "PUT")!.body).toEqual({ status: "sent" });
    expect(await screen.findByText("Moved to Sent.")).toBeInTheDocument();
  });
});

describe("responsive navigation", () => {
  it("opens and closes the mobile navigation drawer", async () => {
    mockFetch({
      ...sessionOk,
      "GET /api/v1/notifications": { ...page([]), unread: 3 },
      "GET /api/v1/dashboard/summary": { ai_status: { configured: true, simulated: true } },
    });
    renderApp(<AppLayout />);
    expect(await screen.findByRole("link", { name: /Notifications \(3 unread\)/ })).toBeInTheDocument();
    expect(await screen.findByText(/AI results are/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const drawer = screen.getByRole("complementary", { name: "Navigation menu" });
    expect(within(drawer).getByRole("link", { name: "Find Jobs" })).toBeInTheDocument();
    expect(within(drawer).queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
    await userEvent.click(within(drawer).getByRole("button", { name: "Close menu" }));
    expect(screen.queryByRole("complementary", { name: "Navigation menu" })).not.toBeInTheDocument();
  });
});
