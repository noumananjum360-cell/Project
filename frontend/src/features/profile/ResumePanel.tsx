import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { SimulatedBadge } from "@/components/domain";
import { ConfirmDialog, useToast } from "@/components/ui/overlays";
import { Badge, Button, Card, CardHeader, Field, Input, Notice, Textarea } from "@/components/ui/primitives";
import { ApiError, errorMessage } from "@/lib/api";
import { profileApi } from "@/services";
import type { Resume } from "@/types/api";

const MAX_MB = 5;

function Review({ resume, onApplied }: { resume: Resume; onApplied: () => void }) {
  const data = resume.extracted_data!;
  const qc = useQueryClient();
  const toast = useToast();
  const [skills, setSkills] = useState<Record<string, "primary" | "additional" | "skip">>(
    Object.fromEntries((data.skills ?? []).map((s) => [s, "additional"])),
  );
  const [fields, setFields] = useState({
    full_name: data.full_name ?? "",
    headline: data.headline ?? "",
    overview: data.overview ?? "",
    years_experience: data.years_experience?.toString() ?? "",
  });
  const [use, setUse] = useState({ full_name: false, headline: false, overview: false, years_experience: false });

  const apply = useMutation({
    mutationFn: () =>
      profileApi.applyResume({
        full_name: use.full_name ? fields.full_name : null,
        headline: use.headline ? fields.headline : null,
        overview: use.overview ? fields.overview : null,
        years_experience: use.years_experience && fields.years_experience ? Number(fields.years_experience) : null,
        add_primary_skills: Object.entries(skills).filter(([, v]) => v === "primary").map(([k]) => k),
        add_additional_skills: Object.entries(skills).filter(([, v]) => v === "additional").map(([k]) => k),
        languages: data.languages ?? [],
      }),
    onSuccess: (p) => {
      qc.setQueryData(["profile"], p);
      qc.invalidateQueries({ queryKey: ["resume"] });
      toast.success("Confirmed details were added to your profile.");
      onApplied();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <div className="space-y-5">
      <Notice tone="warn">
        Review every item. Extracted information is <strong>unverified</strong> until you confirm it; nothing is added to your profile automatically.
      </Notice>
      {data.notice && <Notice tone="neutral">{data.notice}</Notice>}
      {(["full_name", "headline", "years_experience"] as const).map((k) => (
        <div key={k} className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <Field label={{ full_name: "Name", headline: "Headline", years_experience: "Years of experience" }[k]} htmlFor={`rv-${k}`} className="flex-1">
            <Input id={`rv-${k}`} value={fields[k]} onChange={(e) => setFields({ ...fields, [k]: e.target.value })} />
          </Field>
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input type="checkbox" checked={use[k]} onChange={(e) => setUse({ ...use, [k]: e.target.checked })} /> Use
          </label>
        </div>
      ))}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <Field label="Overview" htmlFor="rv-overview" className="flex-1">
          <Textarea id="rv-overview" rows={4} value={fields.overview} onChange={(e) => setFields({ ...fields, overview: e.target.value })} />
        </Field>
        <label className="flex items-center gap-2 pb-2 text-sm">
          <input type="checkbox" checked={use.overview} onChange={(e) => setUse({ ...use, overview: e.target.checked })} /> Use
        </label>
      </div>
      <div>
        <p className="mb-2 text-sm font-medium text-ink-soft">Detected skills</p>
        {Object.keys(skills).length === 0 ? (
          <p className="text-sm text-muted">No skills detected.</p>
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2">
            {Object.entries(skills).map(([s, v]) => (
              <li key={s} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 text-sm">
                <span className="truncate">{s}</span>
                <select
                  aria-label={`How to use skill ${s}`}
                  className="rounded-md border border-line px-2 py-1 text-xs"
                  value={v}
                  onChange={(e) => setSkills({ ...skills, [s]: e.target.value as "primary" | "additional" | "skip" })}
                >
                  <option value="primary">Primary</option>
                  <option value="additional">Additional</option>
                  <option value="skip">Skip</option>
                </select>
              </li>
            ))}
          </ul>
        )}
      </div>
      {!!data.experience?.length && (
        <div>
          <p className="mb-2 text-sm font-medium text-ink-soft">Experience found (for your reference, not added automatically)</p>
          <ul className="space-y-1 text-sm text-muted">
            {data.experience.map((x, i) => (
              <li key={i}>
                {x.title}
                {x.organization ? ` — ${x.organization}` : ""} {x.period ? `(${x.period})` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex justify-end">
        <Button onClick={() => apply.mutate()} loading={apply.isPending}>
          Add confirmed details to profile
        </Button>
      </div>
    </div>
  );
}

export function ResumePanel() {
  const qc = useQueryClient();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const resume = useQuery({
    queryKey: ["resume"],
    queryFn: profileApi.resume,
    retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2,
  });
  const upload = useMutation({
    mutationFn: (f: File) => profileApi.uploadResume(f),
    onSuccess: (r) => {
      qc.setQueryData(["resume"], r);
      setReviewing(true);
      toast.success("Resume processed. Review the extracted details below.");
    },
    onError: (e) => {
      toast.error(errorMessage(e));
      qc.invalidateQueries({ queryKey: ["resume"] });
    },
  });
  const del = useMutation({
    mutationFn: profileApi.deleteResume,
    onSuccess: () => {
      qc.removeQueries({ queryKey: ["resume"] });
      qc.invalidateQueries({ queryKey: ["resume"] });
      setConfirmDelete(false);
      toast.success("Resume data deleted.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const onFile = (f: File | undefined) => {
    if (!f) return;
    const ext = f.name.toLowerCase().split(".").pop();
    if (!["pdf", "docx"].includes(ext ?? "")) return toast.error("Please choose a PDF or DOCX file.");
    if (f.size > MAX_MB * 1024 * 1024) return toast.error(`File exceeds the ${MAX_MB} MB limit.`);
    upload.mutate(f);
  };
  const r = resume.data;

  return (
    <Card>
      <CardHeader
        title="Resume upload"
        description="PDF or DOCX, up to 5 MB. Files are processed in memory and not retained unless your administrator enables retention."
        action={
          <div className="flex gap-2">
            <input ref={input} type="file" accept=".pdf,.docx" className="hidden" aria-label="Choose resume file" onChange={(e) => onFile(e.target.files?.[0])} />
            <Button size="sm" icon={<FileUp className="h-4 w-4" />} loading={upload.isPending} onClick={() => input.current?.click()}>
              Upload resume
            </Button>
            {r && (
              <Button size="sm" variant="outline" icon={<Trash2 className="h-4 w-4" />} onClick={() => setConfirmDelete(true)}>
                Delete
              </Button>
            )}
          </div>
        }
      />
      <div className="p-5">
        {upload.isPending ? (
          <p className="text-sm text-muted">Extracting text and skills…</p>
        ) : !r ? (
          <p className="text-sm text-muted">No resume uploaded. Uploading is optional — you can fill your profile manually.</p>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{r.original_filename}</span>
              <Badge tone={r.status === "failed" ? "bad" : r.status === "applied" ? "good" : "brand"}>{r.status}</Badge>
              {r.extraction_method && <Badge>{r.extraction_method === "ai" ? "AI extraction" : "Keyword extraction"}</Badge>}
              <SimulatedBadge show={r.is_simulated} />
            </div>
            {r.error && <Notice tone="bad">{r.error}</Notice>}
            {r.extracted_data && r.status !== "failed" && (reviewing || r.status === "parsed") ? (
              <Review resume={r} onApplied={() => setReviewing(false)} />
            ) : r.status === "applied" ? (
              <Button variant="outline" size="sm" onClick={() => setReviewing(true)}>
                Review extracted details again
              </Button>
            ) : null}
          </div>
        )}
      </div>
      <ConfirmDialog
        open={confirmDelete}
        title="Delete resume data?"
        message="This removes the uploaded resume, its extracted text and any stored file. Your profile is not changed."
        confirmLabel="Delete"
        danger
        loading={del.isPending}
        onConfirm={() => del.mutate()}
        onCancel={() => setConfirmDelete(false)}
      />
    </Card>
  );
}
