import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { TagInput } from "@/components/domain";
import { Modal, useToast } from "@/components/ui/overlays";
import { Button, Field, Notice, Select, Textarea } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api";
import { portfolioApi, profileApi, proposalsApi } from "@/services";
import type { Length, Tone } from "@/types/api";

export const TONES: Tone[] = ["professional", "friendly", "confident", "concise", "technical"];
export const LENGTHS: Length[] = ["short", "standard", "detailed"];

export function GenerateProposalModal({
  jobId,
  open,
  onClose,
  suggestedProjectIds = [],
}: {
  jobId: string;
  open: boolean;
  onClose: () => void;
  suggestedProjectIds?: string[];
}) {
  const navigate = useNavigate();
  const toast = useToast();
  const profile = useQuery({ queryKey: ["profile"], queryFn: profileApi.get, enabled: open });
  const projects = useQuery({ queryKey: ["portfolio", "all"], queryFn: () => portfolioApi.list({ page_size: 100 }), enabled: open });
  const [tone, setTone] = useState<Tone | "">("");
  const [length, setLength] = useState<Length | "">("");
  const [emphasize, setEmphasize] = useState<string[]>([]);
  const [exclude, setExclude] = useState<string[]>([]);
  const [opening, setOpening] = useState("");
  const [selected, setSelected] = useState<string[] | null>(null);
  const chosen = selected ?? suggestedProjectIds;

  const gen = useMutation({
    mutationFn: () =>
      proposalsApi.generate({
        job_id: jobId,
        tone: tone || undefined,
        length: length || undefined,
        emphasize_skills: emphasize,
        exclude,
        custom_opening: opening.trim() || undefined,
        project_ids: selected === null ? undefined : selected,
      }),
    onSuccess: (p) => {
      toast.success("Proposal generated. Review and edit it before using it.");
      onClose();
      navigate(`/proposals/${p.id}`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const toggle = (id: string) => {
    const cur = new Set(chosen);
    if (cur.has(id)) cur.delete(id);
    else if (cur.size < 5) cur.add(id);
    setSelected([...cur]);
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Write proposal with AI"
      size="lg"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => gen.mutate()} loading={gen.isPending}>
            Generate proposal
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Notice tone="neutral">
          The proposal follows Hook → Solution → Proof → Call to Action and only uses facts from your profile and portfolio. You stay in control: nothing is submitted for you.
        </Notice>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tone" htmlFor="g-tone" hint={`Default: ${profile.data?.proposal_tone ?? "professional"}`}>
            <Select id="g-tone" value={tone} onChange={(e) => setTone(e.target.value as Tone | "")}>
              <option value="">Use my default</option>
              {TONES.map((t) => (
                <option key={t} value={t}>
                  {t[0].toUpperCase() + t.slice(1)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Length" htmlFor="g-len" hint={`Default: ${profile.data?.proposal_length ?? "standard"}`}>
            <Select id="g-len" value={length} onChange={(e) => setLength(e.target.value as Length | "")}>
              <option value="">Use my default</option>
              {LENGTHS.map((l) => (
                <option key={l} value={l}>
                  {l[0].toUpperCase() + l.slice(1)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Emphasize skills" htmlFor="g-emph">
          <TagInput id="g-emph" value={emphasize} onChange={setEmphasize} max={10} />
        </Field>
        <Field label="Your own opening (optional)" htmlFor="g-open" hint="Used as the start of the hook.">
          <Textarea id="g-open" rows={2} maxLength={600} value={opening} onChange={(e) => setOpening(e.target.value)} />
        </Field>
        <Field label="Details to exclude" htmlFor="g-excl" hint="e.g. a previous employer name">
          <TagInput id="g-excl" value={exclude} onChange={setExclude} max={10} />
        </Field>
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-ink-soft">Portfolio projects to reference {selected === null && "(auto-selected by relevance)"}</legend>
          {projects.data?.items.length ? (
            <ul className="max-h-48 space-y-1 overflow-auto rounded-lg border border-line p-2">
              {projects.data.items.map((p) => (
                <li key={p.id}>
                  <label className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-slate-50">
                    <input type="checkbox" checked={chosen.includes(p.id)} onChange={() => toggle(p.id)} />
                    <span className="truncate">{p.title}</span>
                  </label>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No portfolio projects — the proposal will focus honestly on your skills and approach.</p>
          )}
        </fieldset>
      </div>
    </Modal>
  );
}
