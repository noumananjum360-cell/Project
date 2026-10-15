import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Copy, Download, History, KanbanSquare, RefreshCw, Save, Trash2, Wand2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { DemoBadge, formatDate, SimulatedBadge } from "@/components/domain";
import { ConfirmDialog, Modal, useToast } from "@/components/ui/overlays";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Field, Notice, PageHeader, Select, Spinner, Textarea } from "@/components/ui/primitives";
import { ApiError, errorMessage } from "@/lib/api";
import { applicationsApi, proposalsApi } from "@/services";
import type { Length, Proposal, Section, Tone } from "@/types/api";
import { LENGTHS, TONES } from "./GenerateProposalModal";

const SECTION_LABELS: Record<Section, string> = { hook: "Hook", solution: "Solution", proof: "Proof", call_to_action: "Call to action" };
const AUTOSAVE_MS = 1200;

type SaveState = "saved" | "dirty" | "saving" | "error";

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  }
}

function VersionHistory({ proposal, open, onClose }: { proposal: Proposal; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const versions = useQuery({ queryKey: ["proposal-versions", proposal.id], queryFn: () => proposalsApi.versions(proposal.id), enabled: open });
  const restore = useMutation({
    mutationFn: (n: number) => proposalsApi.restore(proposal.id, n),
    onSuccess: (p) => {
      qc.setQueryData(["proposal", proposal.id], p);
      qc.invalidateQueries({ queryKey: ["proposal-versions", proposal.id] });
      toast.success("Version restored.");
      onClose();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const sourceLabel = { generated: "Generated", regenerated: "Regenerated", section_regenerated: "Section regenerated", manual: "Saved edit" };
  return (
    <Modal open={open} onClose={onClose} title="Version history" size="lg">
      {!open ? null : versions.isPending ? (
        <Spinner />
      ) : versions.isError ? (
        <ErrorState message={errorMessage(versions.error)} />
      ) : (
        <ol className="space-y-3">
          {versions.data!.map((v) => (
            <li key={v.id} className="rounded-lg border border-line p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-semibold">v{v.version_number}</span>
                  <Badge>{sourceLabel[v.source]}</Badge>
                  <SimulatedBadge show={v.is_simulated} />
                  <span className="text-xs text-muted">{formatDate(v.created_at, true)}</span>
                </div>
                <Button size="sm" variant="outline" loading={restore.isPending && restore.variables === v.version_number} onClick={() => restore.mutate(v.version_number)}>
                  Restore
                </Button>
              </div>
              {v.model && (
                <p className="mt-1 text-xs text-muted">
                  {v.provider}/{v.model} · {v.prompt_version} · tokens in {v.input_tokens ?? "?"} / out {v.output_tokens ?? "?"}
                  {v.estimated_cost ? ` · est. $${Number(v.estimated_cost).toFixed(4)}` : " · cost unavailable"}
                </p>
              )}
              <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-sm text-ink-soft">{v.content}</p>
            </li>
          ))}
        </ol>
      )}
    </Modal>
  );
}

export default function ProposalEditorPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const proposal = useQuery({ queryKey: ["proposal", id], queryFn: () => proposalsApi.get(id) });
  const [content, setContent] = useState("");
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [copied, setCopied] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [tone, setTone] = useState<Tone>("professional");
  const [length, setLength] = useState<Length>("standard");
  const [confirmRegen, setConfirmRegen] = useState<Section | "all" | null>(null);
  const loadedVersion = useRef<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const p = proposal.data;
    if (!p) return;
    const key = `${p.id}:${p.current_version_number}:${p.updated_at}`;
    if (loadedVersion.current !== key && saveState !== "dirty" && saveState !== "saving") {
      loadedVersion.current = key;
      setContent(p.content);
      setTone(p.tone);
      setLength(p.length);
    }
  }, [proposal.data, saveState]);

  const persist = useCallback(
    async (text: string) => {
      setSaveState("saving");
      try {
        const p = await proposalsApi.update(id, { content: text });
        loadedVersion.current = `${p.id}:${p.current_version_number}:${p.updated_at}`;
        qc.setQueryData(["proposal", id], p);
        setSaveState("saved");
      } catch (e) {
        setSaveState("error");
        toast.error(`Autosave failed: ${errorMessage(e)}`);
      }
    },
    [id, qc, toast],
  );

  const onChange = (text: string) => {
    setContent(text);
    setSaveState("dirty");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => persist(text), AUTOSAVE_MS);
  };
  useEffect(() => () => void (timer.current && clearTimeout(timer.current)), []);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (saveState === "dirty" || saveState === "saving") e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [saveState]);

  const flush = async () => {
    if (timer.current) clearTimeout(timer.current);
    if (saveState === "dirty" || saveState === "error") await persist(content);
  };

  const snapshot = useMutation({
    mutationFn: async () => {
      await flush();
      return proposalsApi.snapshot(id);
    },
    onSuccess: (v) => {
      qc.invalidateQueries({ queryKey: ["proposal", id] });
      qc.invalidateQueries({ queryKey: ["proposal-versions", id] });
      toast.success(`Saved as version ${v.version_number}.`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const regen = useMutation({
    mutationFn: async (section: Section | "all") => {
      await flush();
      return proposalsApi.regenerate(id, { section: section === "all" ? undefined : section, tone, length });
    },
    onSuccess: (p) => {
      loadedVersion.current = null;
      setSaveState("saved");
      qc.setQueryData(["proposal", id], p);
      qc.invalidateQueries({ queryKey: ["proposal-versions", id] });
      toast.success("Regenerated. Your previous text is kept in version history.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: () => proposalsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["proposals"] });
      toast.success("Proposal deleted.");
      navigate("/proposals");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const track = useMutation({
    mutationFn: async () => {
      await flush();
      return applicationsApi.create({ job_id: proposal.data!.job_id, proposal_id: id, status: "ready" });
    },
    onSuccess: () => {
      toast.success("Marked Ready to Submit in your tracker. Submit it yourself on the job platform when you're ready.");
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "application_exists") return toast.info("This job is already in your tracker.");
      toast.error(errorMessage(e));
    },
  });

  const onCopy = async () => {
    if (await copyText(content)) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast.success("Copied. Paste it into the application form yourself after a final review.");
    } else toast.error("Could not access the clipboard.");
  };

  const onExport = async (format: "txt" | "md") => {
    try {
      await flush();
      const res = await proposalsApi.exportFile(id, format);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `proposal.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  if (proposal.isLoading) return <Spinner label="Loading proposal" />;
  if (proposal.isError)
    return proposal.error instanceof ApiError && proposal.error.status === 404 ? (
      <EmptyState title="Proposal not found" action={<Link to="/proposals" className="text-brand-600 hover:underline">Back to Proposal Studio</Link>} />
    ) : (
      <ErrorState message={errorMessage(proposal.error)} onRetry={() => proposal.refetch()} />
    );
  const p = proposal.data!;
  const words = content.trim() ? content.trim().split(/\s+/).length : 0;
  const saveLabel = { saved: "All changes saved", dirty: "Unsaved changes…", saving: "Saving…", error: "Save failed" }[saveState];

  return (
    <>
      <Link to="/proposals" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Proposal Studio
      </Link>
      <PageHeader
        title={p.title}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <Link to={`/jobs/${p.job_id}`} className="text-brand-600 hover:underline">
              View job
            </Link>
            · v{p.current_version_number} <SimulatedBadge show={p.is_simulated} /> <DemoBadge show={p.is_demo} />
          </span>
        }
        actions={
          <>
            <Button variant="outline" icon={<History className="h-4 w-4" />} onClick={() => setHistoryOpen(true)}>
              History
            </Button>
            <Button variant="outline" icon={<Save className="h-4 w-4" />} loading={snapshot.isPending} onClick={() => snapshot.mutate()}>
              Save version
            </Button>
            <Button icon={copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />} onClick={onCopy}>
              {copied ? "Copied" : "Copy"}
            </Button>
          </>
        }
      />

      {!!p.warnings.length && (
        <div className="mb-4 space-y-2">
          {p.warnings.map((w, i) => (
            <Notice key={i} tone="warn">
              {w}
            </Notice>
          ))}
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[1fr_20rem]">
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-3 text-xs text-muted">
            <span aria-live="polite" className={saveState === "error" ? "text-bad" : undefined}>
              {saveLabel}
            </span>
            <span>
              {words} words · {content.length} characters
            </span>
          </div>
          <label htmlFor="proposal-editor" className="sr-only">
            Proposal text
          </label>
          <Textarea
            id="proposal-editor"
            value={content}
            onChange={(e) => onChange(e.target.value)}
            onBlur={() => saveState === "dirty" && flush()}
            rows={22}
            maxLength={20000}
            className="rounded-none border-0 px-5 py-4 text-[15px] focus:ring-0"
          />
        </Card>

        <aside className="space-y-4">
          <Card>
            <CardHeader title="Regenerate" description="Uses only your verified profile and portfolio." />
            <div className="space-y-3 p-5">
              <Field label="Tone" htmlFor="r-tone">
                <Select id="r-tone" value={tone} onChange={(e) => setTone(e.target.value as Tone)}>
                  {TONES.map((t) => (
                    <option key={t} value={t}>
                      {t[0].toUpperCase() + t.slice(1)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Length" htmlFor="r-len">
                <Select id="r-len" value={length} onChange={(e) => setLength(e.target.value as Length)}>
                  {LENGTHS.map((l) => (
                    <option key={l} value={l}>
                      {l[0].toUpperCase() + l.slice(1)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button className="w-full" icon={<RefreshCw className="h-4 w-4" />} loading={regen.isPending && regen.variables === "all"} onClick={() => setConfirmRegen("all")}>
                Regenerate full proposal
              </Button>
              <p className="pt-1 text-xs font-semibold uppercase tracking-wide text-muted">Regenerate one section</p>
              <div className="grid grid-cols-2 gap-2">
                {(Object.keys(SECTION_LABELS) as Section[]).map((s) => (
                  <Button key={s} size="sm" variant="outline" icon={<Wand2 className="h-3.5 w-3.5" />} loading={regen.isPending && regen.variables === s} onClick={() => setConfirmRegen(s)}>
                    {SECTION_LABELS[s]}
                  </Button>
                ))}
              </div>
            </div>
          </Card>
          <Card>
            <CardHeader title="Use this proposal" />
            <div className="space-y-2 p-5">
              <div className="grid grid-cols-2 gap-2">
                <Button size="sm" variant="outline" icon={<Download className="h-4 w-4" />} onClick={() => onExport("txt")}>
                  .txt
                </Button>
                <Button size="sm" variant="outline" icon={<Download className="h-4 w-4" />} onClick={() => onExport("md")}>
                  .md
                </Button>
              </div>
              <Button size="sm" variant="secondary" className="w-full" icon={<KanbanSquare className="h-4 w-4" />} loading={track.isPending} onClick={() => track.mutate()}>
                Mark Ready to Submit
              </Button>
              <p className="text-xs text-muted">BidGenie never submits proposals for you. Copy it, review it, and submit it yourself.</p>
              <Button size="sm" variant="ghost" className="w-full text-bad" icon={<Trash2 className="h-4 w-4" />} onClick={() => setDeleting(true)}>
                Delete proposal
              </Button>
            </div>
          </Card>
        </aside>
      </div>

      <VersionHistory proposal={p} open={historyOpen} onClose={() => setHistoryOpen(false)} />
      <ConfirmDialog
        open={confirmRegen !== null}
        title={confirmRegen === "all" ? "Regenerate the full proposal?" : `Regenerate the ${confirmRegen ? SECTION_LABELS[confirmRegen as Section] : ""} section?`}
        message="Your current text will be saved in version history first, so you can restore it later."
        confirmLabel="Regenerate"
        onConfirm={() => {
          if (confirmRegen) regen.mutate(confirmRegen);
          setConfirmRegen(null);
        }}
        onCancel={() => setConfirmRegen(null)}
      />
      <ConfirmDialog
        open={deleting}
        title="Delete proposal?"
        message="This proposal and all of its versions will be permanently deleted."
        confirmLabel="Delete"
        danger
        loading={del.isPending}
        onConfirm={() => del.mutate()}
        onCancel={() => setDeleting(false)}
      />
    </>
  );
}
