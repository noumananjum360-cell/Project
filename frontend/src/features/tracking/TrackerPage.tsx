import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { CalendarClock, KanbanSquare, List, Search } from "lucide-react";
import { useEffect, useState, type DragEvent } from "react";
import { Link } from "react-router-dom";
import { DemoBadge, formatDate, ScorePill, STATUS_LABELS, StatusBadge } from "@/components/domain";
import { ConfirmDialog, Modal, useToast } from "@/components/ui/overlays";
import { Button, Card, EmptyState, ErrorState, Field, Input, LinkButton, PageHeader, Select, Skeleton, Textarea } from "@/components/ui/primitives";
import { useDebounce } from "@/hooks/useDebounce";
import { errorMessage } from "@/lib/api";
import { applicationsApi } from "@/services";
import type { Application, AppStatus } from "@/types/api";

export const STATUSES: AppStatus[] = ["draft", "ready", "sent", "interview", "hired", "declined", "archived"];

const toLocalInput = (iso: string | null) => (iso ? new Date(iso).toISOString().slice(0, 16) : "");
const fromLocalInput = (v: string) => (v ? new Date(v).toISOString() : null);

function ApplicationModal({ app, onClose }: { app: Application; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const detail = useQuery({ queryKey: ["application", app.id], queryFn: () => applicationsApi.get(app.id) });
  const a = detail.data ?? app;
  const [form, setForm] = useState({
    status: a.status,
    notes: a.notes ?? "",
    submitted_at: toLocalInput(a.submitted_at),
    interview_at: toLocalInput(a.interview_at),
    follow_up_at: toLocalInput(a.follow_up_at),
    contract_value: a.contract_value ?? "",
    status_note: "",
  });
  const [confirmRemove, setConfirmRemove] = useState(false);
  useEffect(() => {
    if (detail.data)
      setForm((f) => ({
        ...f,
        status: detail.data.status,
        notes: detail.data.notes ?? "",
        submitted_at: toLocalInput(detail.data.submitted_at),
        interview_at: toLocalInput(detail.data.interview_at),
        follow_up_at: toLocalInput(detail.data.follow_up_at),
        contract_value: detail.data.contract_value ?? "",
      }));
  }, [detail.data]);
  const valueValid = form.contract_value === "" || /^\d+(\.\d{1,2})?$/.test(form.contract_value);

  const save = useMutation({
    mutationFn: () =>
      applicationsApi.update(app.id, {
        status: form.status,
        notes: form.notes || null,
        submitted_at: fromLocalInput(form.submitted_at),
        interview_at: fromLocalInput(form.interview_at),
        follow_up_at: fromLocalInput(form.follow_up_at),
        contract_value: form.contract_value || null,
        status_note: form.status_note || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["application", app.id] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Application updated.");
      onClose();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: () => applicationsApi.remove(app.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      toast.success("Removed from tracker.");
      onClose();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <Modal
      open
      onClose={onClose}
      title={a.job_title ?? "Application"}
      size="lg"
      footer={
        <>
          <Button variant="ghost" className="mr-auto text-bad" onClick={() => setConfirmRemove(true)}>
            Remove
          </Button>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!valueValid} loading={save.isPending} onClick={() => save.mutate()}>
            Save
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Status" htmlFor="ap-status" hint="Statuses are only changed by you — nothing is detected or submitted automatically.">
          <Select id="ap-status" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as AppStatus })}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Note for this status change" htmlFor="ap-snote">
          <Input id="ap-snote" maxLength={500} value={form.status_note} onChange={(e) => setForm({ ...form, status_note: e.target.value })} />
        </Field>
        <Field label="Date submitted" htmlFor="ap-sub">
          <Input id="ap-sub" type="datetime-local" value={form.submitted_at} onChange={(e) => setForm({ ...form, submitted_at: e.target.value })} />
        </Field>
        <Field label="Interview date" htmlFor="ap-int">
          <Input id="ap-int" type="datetime-local" value={form.interview_at} onChange={(e) => setForm({ ...form, interview_at: e.target.value })} />
        </Field>
        <Field label="Follow-up reminder" htmlFor="ap-fu">
          <Input id="ap-fu" type="datetime-local" value={form.follow_up_at} onChange={(e) => setForm({ ...form, follow_up_at: e.target.value })} />
        </Field>
        <Field label={`Contract value (${a.contract_currency})`} htmlFor="ap-val" error={valueValid ? undefined : "Enter an amount like 1500 or 1500.50"}>
          <Input id="ap-val" inputMode="decimal" value={form.contract_value} onChange={(e) => setForm({ ...form, contract_value: e.target.value })} />
        </Field>
        <Field label="Notes" htmlFor="ap-notes" className="sm:col-span-2">
          <Textarea id="ap-notes" rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </Field>
      </div>
      <div className="mt-4 flex flex-wrap gap-3 text-sm">
        <Link to={`/jobs/${a.job_id}`} className="text-brand-600 hover:underline">
          Job details
        </Link>
        {a.proposal_id && (
          <Link to={`/proposals/${a.proposal_id}`} className="text-brand-600 hover:underline">
            Proposal (v{a.proposal_version_number})
          </Link>
        )}
      </div>
      <div className="mt-5">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Status history</p>
        <ol className="space-y-1 text-sm text-ink-soft">
          {(detail.data?.history ?? []).map((h) => (
            <li key={h.id}>
              {formatDate(h.created_at, true)} — {h.from_status ? `${STATUS_LABELS[h.from_status as AppStatus]} → ` : ""}
              {STATUS_LABELS[h.to_status as AppStatus]}
              {h.note ? ` (${h.note})` : ""}
            </li>
          ))}
        </ol>
      </div>
      <ConfirmDialog
        open={confirmRemove}
        title="Remove from tracker?"
        message="The tracking record and its status history will be deleted. The job and proposal are kept."
        confirmLabel="Remove"
        danger
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
        onCancel={() => setConfirmRemove(false)}
      />
    </Modal>
  );
}

export default function TrackerPage() {
  const [view, setView] = useState<"board" | "list">(() => {
    try {
      return localStorage.getItem("tracker-view") === "list" ? "list" : "board";
    } catch {
      return "board";
    }
  });
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<Application | null>(null);
  const [dragOver, setDragOver] = useState<AppStatus | null>(null);
  const dq = useDebounce(q);
  const qc = useQueryClient();
  const toast = useToast();
  const list = useQuery({
    queryKey: ["applications", dq, statusFilter],
    queryFn: () => applicationsApi.list({ q: dq, status: statusFilter, page_size: 200 }),
  });
  const move = useMutation({
    mutationFn: ({ id, status }: { id: string; status: AppStatus }) => applicationsApi.update(id, { status }),
    onSuccess: (a) => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success(`Moved to ${STATUS_LABELS[a.status]}.`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  useEffect(() => {
    try {
      localStorage.setItem("tracker-view", view);
    } catch {
      /* storage unavailable (private mode) — view preference is not persisted */
    }
  }, [view]);

  const items = list.data?.items ?? [];
  const onDrop = (status: AppStatus) => (e: DragEvent) => {
    e.preventDefault();
    setDragOver(null);
    const id = e.dataTransfer.getData("text/plain");
    const app = items.find((x) => x.id === id);
    if (app && app.status !== status) move.mutate({ id, status });
  };

  return (
    <>
      <PageHeader
        title="Application Tracker"
        description="Track applications you've submitted yourself. Statuses are entered by you."
        actions={
          <div className="flex rounded-lg border border-line bg-white p-0.5" role="group" aria-label="View">
            <Button size="sm" variant={view === "board" ? "secondary" : "ghost"} icon={<KanbanSquare className="h-4 w-4" />} aria-pressed={view === "board"} onClick={() => setView("board")}>
              Board
            </Button>
            <Button size="sm" variant={view === "list" ? "secondary" : "ghost"} icon={<List className="h-4 w-4" />} aria-pressed={view === "list"} onClick={() => setView("list")}>
              List
            </Button>
          </div>
        }
      />
      <Card className="mb-4 flex flex-col gap-3 p-4 sm:flex-row">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted" aria-hidden />
          <Input aria-label="Search applications" placeholder="Search job title or notes" className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Select aria-label="Filter by status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="sm:w-52">
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </Select>
      </Card>

      {list.isLoading ? (
        <Skeleton className="h-72" />
      ) : list.isError ? (
        <ErrorState message={errorMessage(list.error)} onRetry={() => list.refetch()} />
      ) : !items.length ? (
        <Card>
          <EmptyState
            icon={<KanbanSquare className="h-6 w-6" />}
            title={dq || statusFilter ? "No applications match" : "Nothing tracked yet"}
            description="From a job or proposal, choose “Track application” to add it here."
            action={!dq && !statusFilter && <LinkButton to="/jobs">Go to jobs</LinkButton>}
          />
        </Card>
      ) : view === "list" ? (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Job</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Fit</th>
                  <th className="px-4 py-3 font-medium">Follow-up</th>
                  <th className="px-4 py-3 font-medium">Updated</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {items.map((a) => (
                  <tr key={a.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setSelected(a)}>
                    <td className="px-4 py-3">
                      <button className="text-left font-medium text-ink hover:underline" onClick={() => setSelected(a)}>
                        {a.job_title}
                      </button>{" "}
                      <DemoBadge show={a.is_demo} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={a.status} />
                    </td>
                    <td className="px-4 py-3">
                      <ScorePill score={a.job_fit_score} />
                    </td>
                    <td className="px-4 py-3 text-muted">{formatDate(a.follow_up_at)}</td>
                    <td className="px-4 py-3 text-muted">{formatDate(a.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : (
        <div className="-mx-4 overflow-x-auto px-4 pb-2 sm:mx-0 sm:px-0">
          <div className="flex gap-3" style={{ minWidth: `${STATUSES.length * 15}rem` }}>
            {STATUSES.map((s) => {
              const col = items.filter((a) => a.status === s);
              return (
                <section
                  key={s}
                  aria-label={`${STATUS_LABELS[s]} column`}
                  onDragOver={(e) => (e.preventDefault(), setDragOver(s))}
                  onDragLeave={() => setDragOver(null)}
                  onDrop={onDrop(s)}
                  className={clsx("w-60 shrink-0 rounded-xl border bg-slate-50 p-2", dragOver === s ? "border-brand-500" : "border-line")}
                >
                  <h2 className="flex items-center justify-between px-1 pb-2 text-sm font-semibold text-ink">
                    {STATUS_LABELS[s]} <span className="text-xs font-normal text-muted">{col.length}</span>
                  </h2>
                  <ul className="space-y-2">
                    {col.map((a) => (
                      <li
                        key={a.id}
                        draggable
                        onDragStart={(e) => e.dataTransfer.setData("text/plain", a.id)}
                        className="rounded-lg border border-line bg-white p-3 shadow-sm"
                      >
                        <button className="w-full text-left text-sm font-medium text-ink hover:underline" onClick={() => setSelected(a)}>
                          {a.job_title}
                        </button>
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          <ScorePill score={a.job_fit_score} />
                          <DemoBadge show={a.is_demo} />
                          {a.follow_up_at && (
                            <span className="inline-flex items-center gap-1 text-xs text-muted">
                              <CalendarClock className="h-3 w-3" /> {formatDate(a.follow_up_at)}
                            </span>
                          )}
                        </div>
                        <label className="sr-only" htmlFor={`mv-${a.id}`}>
                          Move {a.job_title} to status
                        </label>
                        <Select
                          id={`mv-${a.id}`}
                          className="mt-2 h-8 text-xs"
                          value={a.status}
                          onChange={(e) => move.mutate({ id: a.id, status: e.target.value as AppStatus })}
                        >
                          {STATUSES.map((x) => (
                            <option key={x} value={x}>
                              {STATUS_LABELS[x]}
                            </option>
                          ))}
                        </Select>
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
          </div>
        </div>
      )}
      {selected && <ApplicationModal app={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
