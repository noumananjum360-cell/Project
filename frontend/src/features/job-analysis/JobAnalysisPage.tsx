import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Gauge } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { DemoBadge, formatDate, RecommendationBadge, ScorePill } from "@/components/domain";
import { Card, EmptyState, ErrorState, LinkButton, PageHeader, Pagination, Select, Skeleton } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api";
import { jobsApi } from "@/services";

export default function JobAnalysisPage() {
  const [page, setPage] = useState(1);
  const [minScore, setMinScore] = useState("");
  const analyzed = useQuery({
    queryKey: ["jobs", "analyzed", minScore, page],
    queryFn: () => jobsApi.list({ analyzed: true, sort: "score", min_score: minScore || undefined, page, page_size: 20 }),
    placeholderData: keepPreviousData,
  });
  const pending = useQuery({ queryKey: ["jobs", "pending-count"], queryFn: () => jobsApi.list({ analyzed: false, page_size: 1 }) });

  return (
    <>
      <PageHeader
        title="Job Analysis"
        description="Analyzed jobs ranked by Fit Score."
        actions={
          <Select aria-label="Minimum Fit Score" value={minScore} onChange={(e) => (setMinScore(e.target.value), setPage(1))} className="w-48">
            <option value="">All scores</option>
            <option value="75">Strong (75+)</option>
            <option value="50">50 and above</option>
          </Select>
        }
      />
      {!!pending.data?.total && (
        <Card className="mb-4 flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
          <span>
            {pending.data.total} imported job{pending.data.total === 1 ? "" : "s"} not analyzed yet.
          </span>
          <LinkButton to="/jobs?analyzed=false" size="sm" variant="secondary">
            Review unanalyzed jobs
          </LinkButton>
        </Card>
      )}
      {analyzed.isLoading ? (
        <Skeleton className="h-64" />
      ) : analyzed.isError ? (
        <ErrorState message={errorMessage(analyzed.error)} onRetry={() => analyzed.refetch()} />
      ) : !analyzed.data?.items.length ? (
        <Card>
          <EmptyState icon={<Gauge className="h-6 w-6" />} title="No analyzed jobs" description="Open a job and click “Analyze job” to see its Fit Score here." action={<LinkButton to="/jobs">Go to jobs</LinkButton>} />
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[36rem] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Job</th>
                  <th className="px-4 py-3 font-medium">Score</th>
                  <th className="px-4 py-3 font-medium">Recommendation</th>
                  <th className="px-4 py-3 font-medium">Analyzed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {analyzed.data.items.map((j) => (
                  <tr key={j.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <Link to={`/jobs/${j.id}`} className="font-medium text-ink hover:text-brand-700 hover:underline">
                        {j.title}
                      </Link>{" "}
                      <DemoBadge show={j.is_demo} />
                    </td>
                    <td className="px-4 py-3">
                      <ScorePill score={j.latest_fit_score} />
                    </td>
                    <td className="px-4 py-3">
                      <RecommendationBadge value={j.latest_recommendation} />
                    </td>
                    <td className="px-4 py-3 text-muted">{formatDate(j.analyzed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {analyzed.data && <Pagination page={page} pages={analyzed.data.pages} onChange={setPage} />}
    </>
  );
}
