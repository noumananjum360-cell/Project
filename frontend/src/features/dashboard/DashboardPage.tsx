import { useQuery } from "@tanstack/react-query";
import { Activity, Briefcase, CheckCircle2, Cpu, FileText, Gauge, Send, Star, Trophy, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { DemoBadge, formatDate } from "@/components/domain";
import { Card, CardHeader, EmptyState, ErrorState, LinkButton, PageHeader, Skeleton, StatCard } from "@/components/ui/primitives";
import { useAuth } from "@/features/auth/AuthProvider";
import { errorMessage } from "@/lib/api";
import { dashboardApi } from "@/services";

const EVENT_LABEL = { job_imported: "Imported", job_analyzed: "Analyzed", proposal_generated: "Proposal", status_changed: "Status" };

export default function DashboardPage() {
  const { user } = useAuth();
  const summary = useQuery({ queryKey: ["dashboard", "summary"], queryFn: dashboardApi.summary });
  const analytics = useQuery({ queryKey: ["dashboard", "analytics", 30], queryFn: () => dashboardApi.analytics(30) });
  const activity = useQuery({ queryKey: ["dashboard", "activity"], queryFn: dashboardApi.activity });
  const s = summary.data;

  return (
    <>
      <PageHeader
        title={`Welcome${user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}`}
        description="Your pipeline at a glance. All numbers come from your saved records."
        actions={<LinkButton to="/jobs">Find jobs</LinkButton>}
      />
      {summary.isError ? (
        <ErrorState message={errorMessage(summary.error)} onRetry={() => summary.refetch()} />
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          {!s ? (
            Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-24" />)
          ) : (
            <>
              <StatCard label="Imported jobs" value={s.total_jobs} icon={<Briefcase className="h-4 w-4" />} />
              <StatCard label="Jobs analyzed" value={s.jobs_analyzed} icon={<Gauge className="h-4 w-4" />} />
              <StatCard label="Strong matches" value={s.strong_matches} icon={<Star className="h-4 w-4" />} />
              <StatCard label="Average Fit Score" value={s.average_fit_score ?? "—"} icon={<Activity className="h-4 w-4" />} />
              <StatCard label="Proposals generated" value={s.proposals_generated} icon={<FileText className="h-4 w-4" />} />
              <StatCard label="Proposals sent" value={s.proposals_sent} hint="As marked by you" icon={<Send className="h-4 w-4" />} />
              <StatCard label="Interviews" value={s.interviews} hint="As marked by you" icon={<Users className="h-4 w-4" />} />
              <StatCard label="Hires" value={s.hires} hint="As marked by you" icon={<Trophy className="h-4 w-4" />} />
              <StatCard label="AI requests" value={s.ai_requests} hint={`${(s.ai_input_tokens + s.ai_output_tokens).toLocaleString()} tokens`} icon={<Cpu className="h-4 w-4" />} />
              <StatCard
                label="Est. AI cost"
                value={s.ai_estimated_cost !== null ? `$${s.ai_estimated_cost.toFixed(4)}` : "—"}
                hint={s.ai_estimated_cost === null ? "Pricing not configured" : s.ai_cost_complete ? "Estimate" : "Partial estimate"}
                icon={<CheckCircle2 className="h-4 w-4" />}
              />
            </>
          )}
        </div>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_24rem]">
        <Card>
          <CardHeader title="Activity over the last 30 days" />
          <div className="h-72 p-4">
            {analytics.isLoading ? (
              <Skeleton className="h-full" />
            ) : analytics.data && analytics.data.timeline.some((t) => t.jobs_imported || t.jobs_analyzed || t.proposals) ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={analytics.data.timeline} margin={{ left: -20, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} fontSize={11} />
                  <YAxis allowDecimals={false} fontSize={11} />
                  <Tooltip />
                  <Area type="monotone" dataKey="jobs_imported" name="Imported" stroke="#94a3b8" fill="#e2e8f0" />
                  <Area type="monotone" dataKey="jobs_analyzed" name="Analyzed" stroke="#6366f1" fill="#e0e7ff" />
                  <Area type="monotone" dataKey="proposals" name="Proposals" stroke="#059669" fill="#d1fae5" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState title="No activity yet" description="Import and analyze a job to start seeing trends." />
            )}
          </div>
        </Card>
        <Card>
          <CardHeader title="Recent activity" action={<Link to="/analytics" className="text-sm text-brand-600 hover:underline">Analytics</Link>} />
          {activity.isLoading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-6" />
              <Skeleton className="h-6" />
              <Skeleton className="h-6" />
            </div>
          ) : !activity.data?.length ? (
            <EmptyState title="Nothing here yet" description="Your imports, analyses, proposals and status changes will appear here." />
          ) : (
            <ul className="divide-y divide-line">
              {activity.data.map((e, i) => (
                <li key={i} className="px-5 py-3">
                  <Link to={e.link} className="block hover:underline">
                    <span className="mr-2 text-xs font-semibold uppercase tracking-wide text-brand-600">{EVENT_LABEL[e.type]}</span>
                    <span className="text-sm text-ink">{e.title}</span>
                  </Link>
                  <span className="text-xs text-muted">{formatDate(e.at, true)}</span> <DemoBadge show={e.is_demo} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      {s && s.total_jobs === 0 && (
        <Card className="mt-6 p-5">
          <h2 className="font-semibold">Get started</h2>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-ink-soft">
            <li>
              Complete your <Link to="/profile" className="text-brand-600 hover:underline">profile</Link> with skills and rates.
            </li>
            <li>
              Add a few <Link to="/portfolio" className="text-brand-600 hover:underline">portfolio projects</Link>.
            </li>
            <li>
              <Link to="/jobs" className="text-brand-600 hover:underline">Import a job</Link> and click Analyze.
            </li>
          </ol>
        </Card>
      )}
      {s && <p className="mt-4 text-xs text-muted">{s.notes}</p>}
    </>
  );
}
