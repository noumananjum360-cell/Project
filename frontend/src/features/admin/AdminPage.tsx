import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useEffect, useState } from "react";
import { formatDate } from "@/components/domain";
import { useToast } from "@/components/ui/overlays";
import { Badge, Button, Card, CardHeader, ErrorState, Field, Input, Notice, PageHeader, Pagination, Skeleton, StatCard } from "@/components/ui/primitives";
import { useDebounce } from "@/hooks/useDebounce";
import { errorMessage } from "@/lib/api";
import { adminApi } from "@/services";

type Tab = "users" | "usage" | "health" | "scoring" | "ai" | "audit";

function UsersTab() {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const dq = useDebounce(q);
  const qc = useQueryClient();
  const toast = useToast();
  const users = useQuery({ queryKey: ["admin", "users", dq, page], queryFn: () => adminApi.users({ q: dq, page }), placeholderData: keepPreviousData });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { is_active?: boolean; role?: string } }) => adminApi.updateUser(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      toast.success("User updated. The change was recorded in the audit log.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader title="Users" description="Account metadata only. User content is not accessible from this panel." />
      <div className="p-4">
        <Input aria-label="Search users" placeholder="Search by email or name" value={q} onChange={(e) => (setQ(e.target.value), setPage(1))} />
      </div>
      {users.isLoading ? (
        <Skeleton className="m-4 h-40" />
      ) : users.isError ? (
        <div className="p-4">
          <ErrorState message={errorMessage(users.error)} />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Email</th>
                <th className="px-4 py-2 font-medium">Role</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Registered</th>
                <th className="px-4 py-2 font-medium">Last login</th>
                <th className="px-4 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {users.data!.items.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-2">
                    {u.email}
                    <div className="text-xs text-muted">{u.full_name}</div>
                  </td>
                  <td className="px-4 py-2">
                    <Badge tone={u.role === "ADMIN" ? "brand" : "neutral"}>{u.role}</Badge>
                  </td>
                  <td className="px-4 py-2">{u.is_active ? <Badge tone="good">Active</Badge> : <Badge tone="bad">Deactivated</Badge>}</td>
                  <td className="px-4 py-2 text-muted">{formatDate(u.created_at)}</td>
                  <td className="px-4 py-2 text-muted">{formatDate(u.last_login_at)}</td>
                  <td className="px-4 py-2">
                    <Button size="sm" variant="outline" onClick={() => update.mutate({ id: u.id, body: { is_active: !u.is_active } })}>
                      {u.is_active ? "Deactivate" : "Activate"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 pb-4">
            <Pagination page={page} pages={users.data!.pages} onChange={setPage} />
          </div>
        </div>
      )}
    </Card>
  );
}

interface Usage {
  totals: Record<string, number>;
  ai_by_operation: { operation: string; provider: string; model: string; requests: number; successes: number; input_tokens: number; output_tokens: number; estimated_cost: number | null }[];
  ai_errors: { error_code: string; count: number }[];
  usage_limits: { daily_ai_requests_per_user: number };
}

function UsageTab() {
  const usage = useQuery({ queryKey: ["admin", "usage"], queryFn: () => adminApi.usage(30) as Promise<unknown> as Promise<Usage> });
  if (usage.isLoading) return <Skeleton className="h-48" />;
  if (usage.isError) return <ErrorState message={errorMessage(usage.error)} />;
  const u = usage.data!;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        {Object.entries(u.totals).map(([k, v]) => (
          <StatCard key={k} label={k.replace(/_/g, " ")} value={v} />
        ))}
      </div>
      <Card>
        <CardHeader title="AI usage (last 30 days)" />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-muted">
              <tr>
                {["Operation", "Provider / model", "Requests", "Success", "Tokens in/out", "Est. cost"].map((h) => (
                  <th key={h} className="px-4 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {u.ai_by_operation.map((r, i) => (
                <tr key={i}>
                  <td className="px-4 py-2">{r.operation}</td>
                  <td className="px-4 py-2 text-muted">
                    {r.provider} / {r.model}
                  </td>
                  <td className="px-4 py-2">{r.requests}</td>
                  <td className="px-4 py-2">{r.successes}</td>
                  <td className="px-4 py-2">
                    {r.input_tokens.toLocaleString()} / {r.output_tokens.toLocaleString()}
                  </td>
                  <td className="px-4 py-2">{r.estimated_cost !== null ? `$${r.estimated_cost.toFixed(4)}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card>
        <CardHeader title="AI errors" />
        <div className="p-5 text-sm">
          {u.ai_errors.length ? (
            <ul className="space-y-1">
              {u.ai_errors.map((e) => (
                <li key={e.error_code}>
                  <code>{e.error_code}</code>: {e.count}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted">No AI errors recorded.</p>
          )}
        </div>
      </Card>
    </div>
  );
}

function HealthTab() {
  const health = useQuery({ queryKey: ["admin", "health"], queryFn: adminApi.health, refetchInterval: 30_000 });
  if (health.isLoading) return <Skeleton className="h-48" />;
  if (health.isError) return <ErrorState message={errorMessage(health.error)} />;
  return (
    <Card>
      <CardHeader title="Operational health" description="Refreshes every 30 seconds. Secret values are never shown." />
      <pre className="overflow-x-auto p-5 text-xs text-ink-soft">{JSON.stringify(health.data, null, 2)}</pre>
    </Card>
  );
}

const FACTORS = ["skills", "portfolio", "experience", "budget", "scope", "risk"] as const;

function ScoringTab() {
  const qc = useQueryClient();
  const toast = useToast();
  const cfg = useQuery({ queryKey: ["admin", "scoring"], queryFn: adminApi.scoring });
  const [form, setForm] = useState<Record<string, number> | null>(null);
  useEffect(() => {
    if (cfg.data) setForm({ ...cfg.data.weights, ...cfg.data.thresholds });
  }, [cfg.data]);
  const save = useMutation({
    mutationFn: (v: Record<string, number>) => adminApi.updateScoring(v),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "scoring"] });
      toast.success("Scoring configuration saved. New analyses will use it.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!form) return <Skeleton className="h-48" />;
  const total = FACTORS.reduce((s, k) => s + (Number(form[k]) || 0), 0);
  return (
    <Card>
      <CardHeader title="Fit Score weights & thresholds" description="Weights must total 100. Unknown factors are redistributed automatically." />
      <div className="grid gap-4 p-5 sm:grid-cols-3">
        {[...FACTORS, "strong", "possible", "min_confidence", "similarity_floor", "similarity_ceiling"].map((k) => (
          <Field key={k} label={k.replace(/_/g, " ")} htmlFor={`sc-${k}`}>
            <Input id={`sc-${k}`} type="number" step="any" value={form[k] ?? ""} onChange={(e) => setForm({ ...form, [k]: Number(e.target.value) })} />
          </Field>
        ))}
        <div className="flex items-center justify-between gap-3 sm:col-span-3">
          <span className={clsx("text-sm", Math.abs(total - 100) > 0.01 ? "text-bad" : "text-good")}>Weights total: {total}</span>
          <Button loading={save.isPending} disabled={Math.abs(total - 100) > 0.01} onClick={() => save.mutate(form)}>
            Save scoring config
          </Button>
        </div>
      </div>
    </Card>
  );
}

function AITab() {
  const qc = useQueryClient();
  const toast = useToast();
  const cfg = useQuery({ queryKey: ["admin", "ai"], queryFn: adminApi.aiConfig });
  const usage = useQuery({ queryKey: ["admin", "usage"], queryFn: () => adminApi.usage(30) as Promise<unknown> as Promise<Usage> });
  const [form, setForm] = useState({ chat_model: "", embedding_model: "", timeout_seconds: "" });
  const [limit, setLimit] = useState("");
  useEffect(() => {
    const o = cfg.data?.overrides as Record<string, string | number | null> | undefined;
    if (o) setForm({ chat_model: String(o.chat_model ?? ""), embedding_model: String(o.embedding_model ?? ""), timeout_seconds: String(o.timeout_seconds ?? "") });
  }, [cfg.data]);
  useEffect(() => {
    if (usage.data) setLimit(String(usage.data.usage_limits.daily_ai_requests_per_user));
  }, [usage.data]);
  const save = useMutation({
    mutationFn: () =>
      adminApi.updateAiConfig({
        chat_model: form.chat_model || null,
        embedding_model: form.embedding_model || null,
        timeout_seconds: form.timeout_seconds ? Number(form.timeout_seconds) : null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "ai"] });
      toast.success("AI settings saved.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const saveLimit = useMutation({
    mutationFn: () => adminApi.updateLimits({ daily_ai_requests_per_user: Number(limit) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "usage"] });
      toast.success("Usage limit saved.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title="AI provider settings" description="API keys are configured only through server environment variables and are never displayed." />
        <div className="space-y-4 p-5">
          {cfg.data && (
            <Notice tone={cfg.data.status.configured ? "good" : "warn"}>
              Provider: <strong>{String(cfg.data.status.provider)}</strong> · {cfg.data.status.configured ? "configured" : "NOT configured"}
              {cfg.data.status.simulated ? " · simulated (demo/test only)" : ""}
            </Notice>
          )}
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Chat model override" htmlFor="ai-chat" hint="Blank = use OPENAI_MODEL">
              <Input id="ai-chat" value={form.chat_model} onChange={(e) => setForm({ ...form, chat_model: e.target.value })} />
            </Field>
            <Field label="Embedding model override" htmlFor="ai-emb" hint="Changing this requires a portfolio reindex">
              <Input id="ai-emb" value={form.embedding_model} onChange={(e) => setForm({ ...form, embedding_model: e.target.value })} />
            </Field>
            <Field label="Request timeout (s)" htmlFor="ai-to">
              <Input id="ai-to" type="number" min={5} max={300} value={form.timeout_seconds} onChange={(e) => setForm({ ...form, timeout_seconds: e.target.value })} />
            </Field>
          </div>
          <div className="flex justify-end">
            <Button loading={save.isPending} onClick={() => save.mutate()}>
              Save AI settings
            </Button>
          </div>
        </div>
      </Card>
      <Card>
        <CardHeader title="Usage limits" />
        <div className="flex flex-wrap items-end gap-3 p-5">
          <Field label="Daily AI requests per user (0 = unlimited)" htmlFor="ai-limit">
            <Input id="ai-limit" type="number" min={0} value={limit} onChange={(e) => setLimit(e.target.value)} className="w-40" />
          </Field>
          <Button loading={saveLimit.isPending} disabled={limit === "" || Number(limit) < 0} onClick={() => saveLimit.mutate()}>
            Save limit
          </Button>
        </div>
      </Card>
    </div>
  );
}

function AuditTab() {
  const [page, setPage] = useState(1);
  const logs = useQuery({ queryKey: ["admin", "audit", page], queryFn: () => adminApi.auditLogs({ page }), placeholderData: keepPreviousData });
  if (logs.isLoading) return <Skeleton className="h-48" />;
  if (logs.isError) return <ErrorState message={errorMessage(logs.error)} />;
  return (
    <Card>
      <CardHeader title="Audit events" />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-muted">
            <tr>
              {["When", "Action", "Target", "IP", "Details"].map((h) => (
                <th key={h} className="px-4 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {logs.data!.items.map((a) => (
              <tr key={String(a.id)}>
                <td className="px-4 py-2 text-muted">{formatDate(String(a.created_at), true)}</td>
                <td className="px-4 py-2 font-mono text-xs">{String(a.action)}</td>
                <td className="px-4 py-2 text-xs text-muted">{a.target_type ? `${a.target_type}:${String(a.target_id).slice(0, 8)}` : "—"}</td>
                <td className="px-4 py-2 text-xs text-muted">{String(a.ip_address ?? "—")}</td>
                <td className="px-4 py-2 font-mono text-xs text-muted">{JSON.stringify(a.details)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="px-4 pb-4">
        <Pagination page={page} pages={logs.data!.pages} onChange={setPage} />
      </div>
    </Card>
  );
}

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("users");
  const tabs: [Tab, string][] = [
    ["users", "Users"],
    ["usage", "Usage"],
    ["health", "Health"],
    ["scoring", "Scoring"],
    ["ai", "AI & limits"],
    ["audit", "Audit log"],
  ];
  return (
    <>
      <PageHeader title="Admin" description="Administrative actions are enforced on the server and recorded in the audit log." />
      <div role="tablist" aria-label="Admin sections" className="mb-4 flex gap-1 overflow-x-auto rounded-lg bg-slate-100 p-1">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={clsx("whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium", tab === id ? "bg-white shadow-sm" : "text-muted")}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "users" && <UsersTab />}
      {tab === "usage" && <UsageTab />}
      {tab === "health" && <HealthTab />}
      {tab === "scoring" && <ScoringTab />}
      {tab === "ai" && <AITab />}
      {tab === "audit" && <AuditTab />}
    </>
  );
}
