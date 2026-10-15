import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, Gauge, KanbanSquare, Pencil, PenLine, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { DemoBadge, formatDate, formatMoney, SkillChips } from "@/components/domain";
import { ConfirmDialog, Modal, useToast } from "@/components/ui/overlays";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Notice, PageHeader, Select, Skeleton, Spinner } from "@/components/ui/primitives";
import { AnalysisView } from "@/features/job-analysis/AnalysisView";
import { GenerateProposalModal } from "@/features/proposals/GenerateProposalModal";
import { ApiError, errorMessage } from "@/lib/api";
import { applicationsApi, jobsApi, proposalsApi } from "@/services";
import type { JobStatus } from "@/types/api";
import { JobForm } from "./JobForm";

export default function JobDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [genOpen, setGenOpen] = useState(false);

  const job = useQuery({ queryKey: ["job", id], queryFn: () => jobsApi.get(id) });
  const analysis = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => jobsApi.analysis(id),
    retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2,
  });
  const proposals = useQuery({ queryKey: ["proposals", { job: id }], queryFn: () => proposalsApi.list({ job_id: id }) });

  const analyze = useMutation({
    mutationFn: () => jobsApi.analyze(id),
    onSuccess: (a) => {
      qc.setQueryData(["analysis", id], a);
      qc.invalidateQueries({ queryKey: ["job", id] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["notifications"] });
      toast.success(`Analysis complete: Fit Score ${a.fit_score}.`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const update = useMutation({
    mutationFn: (body: Parameters<typeof jobsApi.update>[1]) => jobsApi.update(id, body),
    onSuccess: (j) => {
      qc.setQueryData(["job", id], j);
      qc.invalidateQueries({ queryKey: ["jobs"] });
      setEditing(false);
      toast.success("Job updated. Re-analyze to refresh the score.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const setStatus = useMutation({
    mutationFn: (status: JobStatus) => jobsApi.patch(id, { status }),
    onSuccess: (j) => {
      qc.setQueryData(["job", id], j);
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: () => jobsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Job deleted.");
      navigate("/jobs");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const track = useMutation({
    mutationFn: () => applicationsApi.create({ job_id: id, proposal_id: proposals.data?.items[0]?.id ?? null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      toast.success("Added to your application tracker.");
      navigate("/tracker");
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "application_exists") {
        navigate("/tracker");
        return;
      }
      toast.error(errorMessage(e));
    },
  });

  if (job.isLoading) return <Spinner label="Loading job" />;
  if (job.isError)
    return job.error instanceof ApiError && job.error.status === 404 ? (
      <EmptyState title="Job not found" description="It may have been deleted." action={<Link to="/jobs" className="text-brand-600 hover:underline">Back to jobs</Link>} />
    ) : (
      <ErrorState message={errorMessage(job.error)} onRetry={() => job.refetch()} />
    );
  const j = job.data!;
  const noAnalysis = analysis.error instanceof ApiError && analysis.error.status === 404;
  const suggested = analysis.data?.result.relevant_portfolio_projects.map((p) => p.project_id) ?? [];

  return (
    <>
      <Link to="/jobs" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> All jobs
      </Link>
      <PageHeader
        title={j.title}
        description={
          <span className="flex flex-wrap items-center gap-2">
            {formatMoney(j.budget_min, j.budget_max, j.currency, j.job_type)} · <span className="capitalize">{j.experience_level}</span> · imported {formatDate(j.created_at)} via {j.source}
            <DemoBadge show={j.is_demo} />
          </span>
        }
        actions={
          <>
            <Button icon={analysis.data ? <RefreshCw className="h-4 w-4" /> : <Gauge className="h-4 w-4" />} loading={analyze.isPending} onClick={() => analyze.mutate()}>
              {analysis.data ? "Re-analyze" : "Analyze job"}
            </Button>
            <Button variant="secondary" icon={<PenLine className="h-4 w-4" />} onClick={() => setGenOpen(true)}>
              Write proposal
            </Button>
          </>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1fr_22rem]">
        <div className="min-w-0 space-y-4">
          {analyze.isPending ? (
            <Card className="p-5">
              <Spinner label="Scoring this job against your profile and portfolio" />
            </Card>
          ) : analysis.isLoading ? (
            <Skeleton className="h-64" />
          ) : analysis.data ? (
            <AnalysisView analysis={analysis.data} />
          ) : noAnalysis ? (
            <Card>
              <EmptyState
                icon={<Gauge className="h-6 w-6" />}
                title="Not analyzed yet"
                description="Run an analysis to get a Fit Score, matched and missing skills, relevant portfolio projects and potential warning signs."
                action={<Button onClick={() => analyze.mutate()} loading={analyze.isPending}>Analyze job</Button>}
              />
            </Card>
          ) : analysis.isError ? (
            <ErrorState message={errorMessage(analysis.error)} onRetry={() => analysis.refetch()} />
          ) : null}
        </div>

        <aside className="space-y-4">
          <Card>
            <CardHeader
              title="Job details"
              action={
                <Button size="sm" variant="ghost" aria-label="Edit job" onClick={() => setEditing(true)}>
                  <Pencil className="h-4 w-4" />
                </Button>
              }
            />
            <div className="space-y-3 p-5 text-sm">
              <div>
                <label htmlFor="job-status" className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Status
                </label>
                <Select id="job-status" className="mt-1" value={j.status} onChange={(e) => setStatus.mutate(e.target.value as JobStatus)}>
                  {["new", "saved", "shortlisted", "applied", "skipped", "archived"].map((s) => (
                    <option key={s} value={s}>
                      {s[0].toUpperCase() + s.slice(1)}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted">Required skills</p>
                <div className="mt-1">
                  <SkillChips skills={j.required_skills} />
                </div>
              </div>
              {j.url && (
                <a href={j.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-brand-600 hover:underline">
                  Open original posting <ExternalLink className="h-3.5 w-3.5" />
                </a>
              )}
              {Object.keys(j.client_info).length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted">Client</p>
                  <ul className="mt-1 space-y-0.5 text-ink-soft">
                    {j.client_info.payment_verified !== undefined && j.client_info.payment_verified !== null && (
                      <li>Payment {j.client_info.payment_verified ? "verified" : "not verified"}</li>
                    )}
                    {j.client_info.rating != null && <li>Rating {j.client_info.rating}/5</li>}
                    {j.client_info.country && <li>{j.client_info.country}</li>}
                  </ul>
                </div>
              )}
              {j.proposals_info && <p className="text-ink-soft">Proposals: {j.proposals_info}</p>}
              {j.notes && <Notice tone="neutral">{j.notes}</Notice>}
              <details>
                <summary className="cursor-pointer text-sm font-medium text-ink">Full description</summary>
                <p className="mt-2 whitespace-pre-wrap text-ink-soft">{j.description}</p>
              </details>
            </div>
          </Card>

          <Card>
            <CardHeader title="Proposals for this job" />
            <div className="p-5">
              {proposals.data?.items.length ? (
                <ul className="space-y-2 text-sm">
                  {proposals.data.items.map((p) => (
                    <li key={p.id} className="flex items-center justify-between gap-2">
                      <Link to={`/proposals/${p.id}`} className="truncate text-brand-600 hover:underline">
                        Version {p.current_version_number} · {p.tone}
                      </Link>
                      <span className="text-xs text-muted">{formatDate(p.updated_at)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted">No proposals yet.</p>
              )}
              <Button variant="outline" size="sm" className="mt-4 w-full" icon={<KanbanSquare className="h-4 w-4" />} loading={track.isPending} onClick={() => track.mutate()}>
                Track application
              </Button>
            </div>
          </Card>

          <Button variant="ghost" className="w-full text-bad" icon={<Trash2 className="h-4 w-4" />} onClick={() => setDeleting(true)}>
            Delete job
          </Button>
          <p className="text-center text-xs text-muted">
            <Badge>Reminder</Badge> BidGenie never applies or spends Connects for you.
          </p>
        </aside>
      </div>

      <Modal open={editing} onClose={() => setEditing(false)} title="Edit job" size="lg">
        <JobForm initial={j} submitLabel="Save changes" loading={update.isPending} onSubmit={(v) => update.mutate({ ...v, status: j.status })} />
      </Modal>
      <ConfirmDialog
        open={deleting}
        title="Delete job?"
        message="The job, its analyses, proposals and tracking records will be permanently deleted."
        confirmLabel="Delete"
        danger
        loading={del.isPending}
        onConfirm={() => del.mutate()}
        onCancel={() => setDeleting(false)}
      />
      <GenerateProposalModal jobId={id} open={genOpen} onClose={() => setGenOpen(false)} suggestedProjectIds={suggested} />
    </>
  );
}
