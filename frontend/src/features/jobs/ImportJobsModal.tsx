import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { FileSpreadsheet } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Modal, useToast } from "@/components/ui/overlays";
import { Button, Field, Notice, Textarea } from "@/components/ui/primitives";
import { ApiError, errorMessage } from "@/lib/api";
import { jobsApi } from "@/services";
import type { JobImport, JobInput } from "@/types/api";
import { JobForm } from "./JobForm";

type Tab = "manual" | "paste" | "csv";

export function ImportJobsModal({ open, onClose, initialTab = "manual" }: { open: boolean; onClose: () => void; initialTab?: Tab }) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [pasted, setPasted] = useState("");
  const [parsed, setParsed] = useState<Partial<JobInput> | null>(null);
  const [csvResult, setCsvResult] = useState<JobImport | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();

  const close = () => {
    setParsed(null);
    setPasted("");
    setCsvResult(null);
    onClose();
  };

  const create = useMutation({
    mutationFn: (v: JobInput) => jobsApi.create(v, tab === "paste" ? "paste" : "manual"),
    onSuccess: (job) => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Job saved.");
      close();
      navigate(`/jobs/${job.id}`);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "duplicate_job") {
        const id = (e.details as { existing_job_id?: string })?.existing_job_id;
        toast.info("This job was already imported — opening the existing record.");
        close();
        if (id) navigate(`/jobs/${id}`);
        return;
      }
      toast.error(errorMessage(e));
    },
  });
  const parse = useMutation({
    mutationFn: () => jobsApi.parseText(pasted),
    onSuccess: setParsed,
    onError: (e) => toast.error(errorMessage(e)),
  });
  const csv = useMutation({
    mutationFn: (f: File) => jobsApi.importCsv(f),
    onSuccess: (r) => {
      setCsvResult(r);
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const tabs: { id: Tab; label: string }[] = [
    { id: "manual", label: "Manual entry" },
    { id: "paste", label: "Paste job post" },
    { id: "csv", label: "CSV import" },
  ];

  return (
    <Modal open={open} onClose={close} title="Add jobs" size="lg">
      <div role="tablist" aria-label="Import method" className="mb-4 flex gap-1 rounded-lg bg-slate-100 p-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={clsx("flex-1 rounded-md px-3 py-1.5 text-sm font-medium", tab === t.id ? "bg-white shadow-sm" : "text-muted")}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "manual" && <JobForm submitLabel="Save job" loading={create.isPending} onSubmit={(v) => create.mutate(v)} />}

      {tab === "paste" &&
        (parsed ? (
          <div className="space-y-4">
            <Notice tone="warn">Review the extracted fields — they were detected automatically from your pasted text and may be incomplete.</Notice>
            <JobForm initial={parsed} submitLabel="Save job" loading={create.isPending} onSubmit={(v) => create.mutate(v)} />
            <Button variant="ghost" size="sm" onClick={() => setParsed(null)}>
              ← Back to pasted text
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <Notice tone="neutral">
              Paste the job title on the first line followed by the description, budget and skills you can see. BidGenie does not fetch pages from job sites.
            </Notice>
            <Field label="Job post text" htmlFor="paste-text">
              <Textarea id="paste-text" rows={10} value={pasted} onChange={(e) => setPasted(e.target.value)} />
            </Field>
            <div className="flex justify-end">
              <Button disabled={pasted.trim().length < 20} loading={parse.isPending} onClick={() => parse.mutate()}>
                Extract fields for review
              </Button>
            </div>
          </div>
        ))}

      {tab === "csv" && (
        <div className="space-y-4">
          <Notice tone="neutral">
            Required columns: <code>title</code>, <code>description</code>. Optional: <code>budget_min</code>, <code>budget_max</code>, <code>currency</code>,{" "}
            <code>job_type</code> (hourly/fixed), <code>required_skills</code> (separated by ; or |), <code>experience_level</code>, <code>url</code>,{" "}
            <code>posted_at</code> (YYYY-MM-DD), <code>notes</code>. Duplicates are skipped automatically.
          </Notice>
          <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" aria-label="Choose CSV file" onChange={(e) => e.target.files?.[0] && csv.mutate(e.target.files[0])} />
          <Button icon={<FileSpreadsheet className="h-4 w-4" />} loading={csv.isPending} onClick={() => fileRef.current?.click()}>
            Choose CSV file
          </Button>
          {csvResult && (
            <div className="space-y-2">
              <Notice tone={csvResult.error_count ? "warn" : "good"}>
                Processed {csvResult.total_rows} rows: {csvResult.created_count} imported, {csvResult.duplicate_count} duplicates skipped,{" "}
                {csvResult.error_count} errors.
              </Notice>
              {!!csvResult.errors.length && (
                <ul className="max-h-40 overflow-auto rounded-lg border border-line p-3 text-xs text-ink-soft">
                  {csvResult.errors.map((er, i) => (
                    <li key={i}>
                      Line {er.line}: {er.error}
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex justify-end">
                <Button variant="outline" onClick={close}>
                  Done
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
