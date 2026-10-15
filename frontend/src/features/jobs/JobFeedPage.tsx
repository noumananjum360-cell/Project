import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Briefcase, Plus, RefreshCw, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { DemoBadge, formatDate, formatMoney, RecommendationBadge, ScorePill, SkillChips } from "@/components/domain";
import { useToast } from "@/components/ui/overlays";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, PageHeader, Pagination, Select, Skeleton } from "@/components/ui/primitives";
import { useDebounce } from "@/hooks/useDebounce";
import { errorMessage } from "@/lib/api";
import { jobsApi } from "@/services";
import { ImportJobsModal } from "./ImportJobsModal";

const FILTER_KEYS = ["q", "exclude", "skills", "budget_min", "budget_max", "job_type", "experience_level", "posted_after", "min_score", "analyzed", "status", "sort"] as const;

export default function JobFeedPage() {
  const [params, setParams] = useSearchParams();
  const [showFilters, setShowFilters] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const page = Number(params.get("page") ?? 1);
  const qc = useQueryClient();
  const toast = useToast();

  const get = (k: string) => params.get(k) ?? "";
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    next.delete("page");
    setParams(next, { replace: true });
  };
  const q = useDebounce(get("q"));
  const exclude = useDebounce(get("exclude"));
  const skills = useDebounce(get("skills"));
  const filters = Object.fromEntries(FILTER_KEYS.map((k) => [k, get(k)]));
  Object.assign(filters, { q, exclude, skills });

  const jobs = useQuery({
    queryKey: ["jobs", filters, page],
    queryFn: () => jobsApi.list({ ...filters, page, page_size: 15 }),
    placeholderData: keepPreviousData,
  });
  const archive = useMutation({
    mutationFn: (id: string) => jobsApi.patch(id, { status: "archived" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      toast.success("Job archived.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const activeFilters = FILTER_KEYS.filter((k) => k !== "sort" && get(k)).length;

  return (
    <>
      <PageHeader
        title="Find Jobs"
        description="Jobs you've imported manually, by pasting, from CSV or with the browser extension."
        actions={
          <>
            <Button variant="outline" icon={<RefreshCw className="h-4 w-4" />} loading={jobs.isFetching && !jobs.isLoading} onClick={() => jobs.refetch()}>
              Refresh
            </Button>
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setImportOpen(true)}>
              Add jobs
            </Button>
          </>
        }
      />

      <Card className="mb-4 p-4">
        <div className="flex flex-col gap-3 sm:flex-row">
          <Input aria-label="Search jobs" placeholder="Include keywords" value={get("q")} onChange={(e) => set("q", e.target.value)} className="sm:flex-1" />
          <Select aria-label="Sort jobs" value={get("sort") || "newest"} onChange={(e) => set("sort", e.target.value)} className="sm:w-44">
            <option value="newest">Newest imported</option>
            <option value="score">Highest Fit Score</option>
            <option value="budget">Highest budget</option>
            <option value="posted">Recently posted</option>
            <option value="oldest">Oldest</option>
          </Select>
          <Button variant="outline" icon={<SlidersHorizontal className="h-4 w-4" />} onClick={() => setShowFilters((s) => !s)} aria-expanded={showFilters}>
            Filters{activeFilters ? ` (${activeFilters})` : ""}
          </Button>
        </div>
        {showFilters && (
          <div className="mt-4 grid gap-3 border-t border-line pt-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Exclude keywords" htmlFor="f-ex">
              <Input id="f-ex" placeholder="comma separated" value={get("exclude")} onChange={(e) => set("exclude", e.target.value)} />
            </Field>
            <Field label="Required skills" htmlFor="f-sk">
              <Input id="f-sk" placeholder="comma separated" value={get("skills")} onChange={(e) => set("skills", e.target.value)} />
            </Field>
            <Field label="Min budget" htmlFor="f-bmin">
              <Input id="f-bmin" inputMode="decimal" value={get("budget_min")} onChange={(e) => set("budget_min", e.target.value.replace(/[^\d.]/g, ""))} />
            </Field>
            <Field label="Max budget" htmlFor="f-bmax">
              <Input id="f-bmax" inputMode="decimal" value={get("budget_max")} onChange={(e) => set("budget_max", e.target.value.replace(/[^\d.]/g, ""))} />
            </Field>
            <Field label="Job type" htmlFor="f-type">
              <Select id="f-type" value={get("job_type")} onChange={(e) => set("job_type", e.target.value)}>
                <option value="">Any</option>
                <option value="hourly">Hourly</option>
                <option value="fixed">Fixed price</option>
                <option value="unknown">Unknown</option>
              </Select>
            </Field>
            <Field label="Experience level" htmlFor="f-lvl">
              <Select id="f-lvl" value={get("experience_level")} onChange={(e) => set("experience_level", e.target.value)}>
                <option value="">Any</option>
                <option value="entry">Entry</option>
                <option value="intermediate">Intermediate</option>
                <option value="expert">Expert</option>
              </Select>
            </Field>
            <Field label="Posted after" htmlFor="f-posted">
              <Input id="f-posted" type="date" value={get("posted_after")} onChange={(e) => set("posted_after", e.target.value)} />
            </Field>
            <Field label="Min Fit Score" htmlFor="f-score">
              <Input id="f-score" inputMode="numeric" value={get("min_score")} onChange={(e) => set("min_score", e.target.value.replace(/\D/g, "").slice(0, 3))} />
            </Field>
            <Field label="Analysis" htmlFor="f-an">
              <Select id="f-an" value={get("analyzed")} onChange={(e) => set("analyzed", e.target.value)}>
                <option value="">All</option>
                <option value="true">Analyzed</option>
                <option value="false">Not analyzed</option>
              </Select>
            </Field>
            <Field label="Status" htmlFor="f-status">
              <Select id="f-status" value={get("status")} onChange={(e) => set("status", e.target.value)}>
                <option value="">Active (not archived)</option>
                <option value="saved,shortlisted">Saved</option>
                <option value="new">New</option>
                <option value="applied">Applied</option>
                <option value="skipped">Skipped</option>
                <option value="archived">Archived</option>
              </Select>
            </Field>
            <div className="flex items-end">
              <Button variant="ghost" onClick={() => setParams(new URLSearchParams(), { replace: true })}>
                Clear filters
              </Button>
            </div>
          </div>
        )}
      </Card>

      {jobs.isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : jobs.isError ? (
        <ErrorState message={errorMessage(jobs.error)} onRetry={() => jobs.refetch()} />
      ) : !jobs.data?.items.length ? (
        <Card>
          <EmptyState
            icon={<Briefcase className="h-6 w-6" />}
            title={activeFilters ? "No jobs match these filters" : "No jobs yet"}
            description={
              activeFilters
                ? "Try widening your filters."
                : "Add a job by pasting its details, entering it manually, importing a CSV, or using the BidGenie browser extension on a job page."
            }
            action={!activeFilters && <Button onClick={() => setImportOpen(true)}>Add your first job</Button>}
          />
        </Card>
      ) : (
        <>
          <ul className="space-y-3">
            {jobs.data.items.map((j) => (
              <li key={j.id}>
                <Card className="p-4 transition-shadow hover:shadow-md sm:p-5">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 flex-1">
                      <Link to={`/jobs/${j.id}`} className="font-semibold text-ink hover:text-brand-700 hover:underline">
                        {j.title}
                      </Link>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                        <span>{formatMoney(j.budget_min, j.budget_max, j.currency, j.job_type)}</span>
                        <span className="capitalize">{j.experience_level !== "unknown" ? j.experience_level : "Level unknown"}</span>
                        <span>Imported {formatDate(j.created_at)}</span>
                        <Badge>{j.source}</Badge>
                        {j.status !== "new" && <Badge tone="brand">{j.status}</Badge>}
                        <DemoBadge show={j.is_demo} />
                      </div>
                      <p className="mt-2 line-clamp-2 text-sm text-ink-soft">{j.description}</p>
                      <div className="mt-2">
                        <SkillChips skills={j.required_skills.slice(0, 8)} />
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2 sm:flex-col sm:items-end">
                      <ScorePill score={j.latest_fit_score} />
                      <RecommendationBadge value={j.latest_recommendation} />
                      <div className="flex gap-1">
                        <Link to={`/jobs/${j.id}`} className="rounded-md px-2 py-1 text-sm font-medium text-brand-600 hover:bg-brand-50">
                          {j.analyzed_at ? "View analysis" : "Analyze"}
                        </Link>
                        {j.status !== "archived" && (
                          <Button size="sm" variant="ghost" aria-label={`Archive ${j.title}`} onClick={() => archive.mutate(j.id)}>
                            <Archive className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
          <Pagination
            page={page}
            pages={jobs.data.pages}
            onChange={(p) => {
              const next = new URLSearchParams(params);
              next.set("page", String(p));
              setParams(next);
            }}
          />
        </>
      )}
      <ImportJobsModal open={importOpen} onClose={() => setImportOpen(false)} />
    </>
  );
}
