import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { FileText, Search } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { DemoBadge, formatDate, SimulatedBadge, StatusBadge } from "@/components/domain";
import { Card, EmptyState, ErrorState, Input, LinkButton, PageHeader, Pagination, Skeleton } from "@/components/ui/primitives";
import { useDebounce } from "@/hooks/useDebounce";
import { errorMessage } from "@/lib/api";
import { proposalsApi } from "@/services";

export default function ProposalStudioPage() {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const dq = useDebounce(q);
  const list = useQuery({
    queryKey: ["proposals", dq, page],
    queryFn: () => proposalsApi.list({ q: dq, page, page_size: 20 }),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title="Proposal Studio"
        description="Every proposal you've generated, with full version history. Open one to edit, regenerate, copy or export."
        actions={<LinkButton to="/jobs">Write a new proposal</LinkButton>}
      />
      <Card className="mb-4 p-4">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted" aria-hidden />
          <Input aria-label="Search proposals" placeholder="Search proposal text or title" className="pl-9" value={q} onChange={(e) => (setQ(e.target.value), setPage(1))} />
        </div>
      </Card>
      {list.isLoading ? (
        <Skeleton className="h-64" />
      ) : list.isError ? (
        <ErrorState message={errorMessage(list.error)} onRetry={() => list.refetch()} />
      ) : !list.data?.items.length ? (
        <Card>
          <EmptyState
            icon={<FileText className="h-6 w-6" />}
            title={dq ? "No proposals match your search" : "No proposals yet"}
            description="Open a job and choose “Write proposal” to generate a personalised draft based on your verified experience."
            action={<LinkButton to="/jobs">Browse your jobs</LinkButton>}
          />
        </Card>
      ) : (
        <Card className="divide-y divide-line">
          {list.data.items.map((p) => (
            <Link key={p.id} to={`/proposals/${p.id}`} className="flex flex-col gap-2 px-5 py-4 hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="truncate font-medium text-ink">{p.job_title ?? p.title}</p>
                <p className="mt-0.5 text-xs text-muted">
                  v{p.current_version_number} · {p.tone} · {p.length} · updated {formatDate(p.updated_at, true)}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {p.application_status && <StatusBadge status={p.application_status} />}
                <SimulatedBadge show={p.is_simulated} />
                <DemoBadge show={p.is_demo} />
              </div>
            </Link>
          ))}
        </Card>
      )}
      {list.data && <Pagination page={page} pages={list.data.pages} onChange={setPage} />}
    </>
  );
}
