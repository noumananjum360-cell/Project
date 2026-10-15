import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { STATUS_LABELS } from "@/components/domain";
import { Card, CardHeader, EmptyState, ErrorState, PageHeader, Select, Skeleton } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api";
import { dashboardApi } from "@/services";

const STATUS_COLORS: Record<string, string> = {
  draft: "#94a3b8",
  ready: "#818cf8",
  sent: "#4f46e5",
  interview: "#d97706",
  hired: "#059669",
  declined: "#dc2626",
  archived: "#cbd5e1",
};

function ChartCard({ title, description, empty, children }: { title: string; description?: string; empty: boolean; children: React.ReactElement }) {
  return (
    <Card>
      <CardHeader title={title} description={description} />
      <div className="h-72 p-4">
        {empty ? <EmptyState title="No data yet" /> : <ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer>}
      </div>
    </Card>
  );
}

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const q = useQuery({ queryKey: ["dashboard", "analytics", days], queryFn: () => dashboardApi.analytics(days) });
  const d = q.data;

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Calculated from your own saved jobs, analyses, proposals and tracker statuses."
        actions={
          <Select aria-label="Time range" value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-40">
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last year</option>
          </Select>
        }
      />
      {q.isLoading ? (
        <div className="grid gap-6 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-80" />
          ))}
        </div>
      ) : q.isError ? (
        <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} />
      ) : (
        d && (
          <div className="grid gap-6 lg:grid-cols-2">
            <ChartCard title="Jobs analyzed over time" empty={!d.timeline.some((t) => t.jobs_analyzed)}>
              <LineChart data={d.timeline} margin={{ left: -20, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tickFormatter={(x: string) => x.slice(5)} fontSize={11} />
                <YAxis allowDecimals={false} fontSize={11} />
                <Tooltip />
                <Line type="monotone" dataKey="jobs_analyzed" name="Analyzed" stroke="#4f46e5" dot={false} />
                <Line type="monotone" dataKey="jobs_imported" name="Imported" stroke="#94a3b8" dot={false} />
              </LineChart>
            </ChartCard>
            <ChartCard title="Fit Score distribution" description="Latest score per job" empty={!d.fit_score_distribution.some((b) => b.count)}>
              <BarChart data={d.fit_score_distribution} margin={{ left: -20, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="range" fontSize={11} />
                <YAxis allowDecimals={false} fontSize={11} />
                <Tooltip />
                <Bar dataKey="count" name="Jobs" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ChartCard>
            <ChartCard title="Proposal status breakdown" description="From your tracker" empty={!d.status_breakdown.some((s) => s.count)}>
              <PieChart>
                <Pie
                  data={d.status_breakdown.filter((s) => s.count).map((s) => ({ ...s, name: STATUS_LABELS[s.status] }))}
                  dataKey="count"
                  nameKey="name"
                  innerRadius={50}
                  outerRadius={90}
                >
                  {d.status_breakdown
                    .filter((s) => s.count)
                    .map((s) => (
                      <Cell key={s.status} fill={STATUS_COLORS[s.status]} />
                    ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ChartCard>
            <ChartCard title="Application outcomes" description="Only outcomes you've recorded" empty={!d.outcomes.some((o) => o.count)}>
              <BarChart data={d.outcomes.map((o) => ({ ...o, label: STATUS_LABELS[o.outcome as keyof typeof STATUS_LABELS] }))} margin={{ left: -20, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="label" fontSize={11} />
                <YAxis allowDecimals={false} fontSize={11} />
                <Tooltip />
                <Bar dataKey="count" name="Applications" radius={[4, 4, 0, 0]}>
                  {d.outcomes.map((o) => (
                    <Cell key={o.outcome} fill={STATUS_COLORS[o.outcome]} />
                  ))}
                </Bar>
              </BarChart>
            </ChartCard>
            <ChartCard title="Proposal activity" empty={!d.timeline.some((t) => t.proposals)}>
              <BarChart data={d.timeline} margin={{ left: -20, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tickFormatter={(x: string) => x.slice(5)} fontSize={11} />
                <YAxis allowDecimals={false} fontSize={11} />
                <Tooltip />
                <Bar dataKey="proposals" name="Proposals" fill="#059669" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ChartCard>
            <ChartCard title="Most frequently matched skills" description="Across your analyzed jobs" empty={!d.top_matched_skills.length}>
              <BarChart data={d.top_matched_skills} layout="vertical" margin={{ left: 20, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis type="number" allowDecimals={false} fontSize={11} />
                <YAxis type="category" dataKey="skill" width={90} fontSize={11} />
                <Tooltip />
                <Bar dataKey="count" name="Jobs" fill="#4f46e5" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ChartCard>
            {!!d.top_missing_skills.length && (
              <Card className="lg:col-span-2">
                <CardHeader title="Most frequently missing skills" description="Skills jobs asked for that aren't on your profile." />
                <div className="flex flex-wrap gap-2 p-5">
                  {d.top_missing_skills.map((s) => (
                    <span key={s.skill} className="rounded-full bg-bad-soft px-3 py-1 text-sm text-bad">
                      {s.skill} · {s.count}
                    </span>
                  ))}
                </div>
              </Card>
            )}
          </div>
        )
      )}
    </>
  );
}
