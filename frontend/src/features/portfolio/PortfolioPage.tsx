import { zodResolver } from "@hookform/resolvers/zod";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FolderKanban, Pencil, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { DemoBadge, SkillChips, TagInput } from "@/components/domain";
import { ConfirmDialog, Modal, useToast } from "@/components/ui/overlays";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  Pagination,
  Skeleton,
  Textarea,
} from "@/components/ui/primitives";
import { useDebounce } from "@/hooks/useDebounce";
import { errorMessage } from "@/lib/api";
import { portfolioApi } from "@/services";
import type { PortfolioProject } from "@/types/api";

const url = z
  .string()
  .trim()
  .refine((v) => v === "" || /^https?:\/\/\S+$/i.test(v), "Use a full http(s):// URL");

const schema = z
  .object({
    title: z.string().trim().min(2, "Title is required").max(200),
    description: z.string().trim().min(10, "Describe the project in at least 10 characters").max(8000),
    skills: z.array(z.string()).max(40),
    category: z.string().trim().max(100),
    role: z.string().trim().max(200),
    achievements: z.string().trim().max(3000),
    url,
    image_url: url,
    start_date: z.string(),
    end_date: z.string(),
    duration_text: z.string().trim().max(100),
  })
  .refine((v) => !v.start_date || !v.end_date || v.end_date >= v.start_date, { path: ["end_date"], message: "End date must be after start date" });
type Values = z.infer<typeof schema>;

const empty: Values = {
  title: "",
  description: "",
  skills: [],
  category: "",
  role: "",
  achievements: "",
  url: "",
  image_url: "",
  start_date: "",
  end_date: "",
  duration_text: "",
};

function toPayload(v: Values) {
  const n = (s: string) => (s === "" ? null : s);
  return {
    ...v,
    category: n(v.category),
    role: n(v.role),
    achievements: n(v.achievements),
    url: n(v.url),
    image_url: n(v.image_url),
    start_date: n(v.start_date),
    end_date: n(v.end_date),
    duration_text: n(v.duration_text),
  };
}

export function PortfolioForm({ project, onDone }: { project?: PortfolioProject; onDone: (p: PortfolioProject) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { register, handleSubmit, control, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: project
      ? {
          title: project.title,
          description: project.description,
          skills: project.skills,
          category: project.category ?? "",
          role: project.role ?? "",
          achievements: project.achievements ?? "",
          url: project.url ?? "",
          image_url: project.image_url ?? "",
          start_date: project.start_date ?? "",
          end_date: project.end_date ?? "",
          duration_text: project.duration_text ?? "",
        }
      : empty,
  });
  const save = useMutation({
    mutationFn: (v: Values) => (project ? portfolioApi.update(project.id, toPayload(v)) : portfolioApi.create(toPayload(v))),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["portfolio"] });
      toast.success(project ? "Project updated." : "Project added.");
      if (p.embedding_status !== "ready")
        toast.info("Saved. Semantic matching for this project will be available once the AI provider is configured.");
      onDone(p);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const e = formState.errors;
  return (
    <form id="portfolio-form" onSubmit={handleSubmit((v) => save.mutate(v))} className="grid gap-4 sm:grid-cols-2" noValidate>
      <Field label="Project title" htmlFor="pf-title" error={e.title?.message} className="sm:col-span-2">
        <Input id="pf-title" {...register("title")} invalid={!!e.title} />
      </Field>
      <Field label="Description" htmlFor="pf-desc" error={e.description?.message} className="sm:col-span-2" hint="Describe what you actually did. Do not include confidential client details.">
        <Textarea id="pf-desc" rows={5} {...register("description")} invalid={!!e.description} />
      </Field>
      <Field label="Skills & technologies" htmlFor="pf-skills" className="sm:col-span-2">
        <Controller control={control} name="skills" render={({ field }) => <TagInput id="pf-skills" value={field.value} onChange={field.onChange} />} />
      </Field>
      <Field label="Category" htmlFor="pf-cat" error={e.category?.message}>
        <Input id="pf-cat" {...register("category")} />
      </Field>
      <Field label="Your role" htmlFor="pf-role" error={e.role?.message}>
        <Input id="pf-role" {...register("role")} />
      </Field>
      <Field label="Verified outcomes (optional)" htmlFor="pf-ach" error={e.achievements?.message} className="sm:col-span-2" hint="Only results you can verify. These may be cited in proposals.">
        <Textarea id="pf-ach" rows={2} {...register("achievements")} />
      </Field>
      <Field label="Public URL" htmlFor="pf-url" error={e.url?.message}>
        <Input id="pf-url" placeholder="https://" {...register("url")} />
      </Field>
      <Field label="Image URL" htmlFor="pf-img" error={e.image_url?.message}>
        <Input id="pf-img" placeholder="https://" {...register("image_url")} />
      </Field>
      <Field label="Start date" htmlFor="pf-start">
        <Input id="pf-start" type="date" {...register("start_date")} />
      </Field>
      <Field label="End date" htmlFor="pf-end" error={e.end_date?.message}>
        <Input id="pf-end" type="date" {...register("end_date")} />
      </Field>
      <Field label="Duration (free text)" htmlFor="pf-dur" className="sm:col-span-2">
        <Input id="pf-dur" placeholder="e.g. 3 months" {...register("duration_text")} />
      </Field>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" loading={save.isPending}>
          {project ? "Save changes" : "Add project"}
        </Button>
      </div>
    </form>
  );
}

function EmbeddingBadge({ p }: { p: PortfolioProject }) {
  if (p.embedding_status === "ready") return <Badge tone="good">Indexed</Badge>;
  if (p.embedding_status === "failed") return <Badge tone="bad">Index failed</Badge>;
  return <Badge tone="warn">Not indexed</Badge>;
}

export default function PortfolioPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [skill, setSkill] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<PortfolioProject | "new" | null>(null);
  const [deleting, setDeleting] = useState<PortfolioProject | null>(null);
  const dq = useDebounce(q);
  const dskill = useDebounce(skill);
  const list = useQuery({
    queryKey: ["portfolio", dq, dskill, page],
    queryFn: () => portfolioApi.list({ q: dq, skill: dskill, page, page_size: 12 }),
    placeholderData: keepPreviousData,
  });
  const del = useMutation({
    mutationFn: (id: string) => portfolioApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["portfolio"] });
      setDeleting(null);
      toast.success("Project deleted and removed from the search index.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const reindex = useMutation({
    mutationFn: () => portfolioApi.reindex(),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["portfolio"] });
      toast.success(`Indexed ${r.indexed}, unchanged ${r.skipped}, failed ${r.failed}.`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <PageHeader
        title="Portfolio"
        description="Projects are embedded for semantic matching against jobs. Only facts you add here are cited in proposals."
        actions={
          <>
            <Button variant="outline" icon={<RefreshCw className="h-4 w-4" />} loading={reindex.isPending} onClick={() => reindex.mutate()}>
              Rebuild index
            </Button>
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setEditing("new")}>
              Add project
            </Button>
          </>
        }
      />
      <Card className="mb-4 p-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted" aria-hidden />
            <Input aria-label="Search projects" placeholder="Search title or description" className="pl-9" value={q} onChange={(e) => (setQ(e.target.value), setPage(1))} />
          </div>
          <Input aria-label="Filter by skill" placeholder="Filter by skill (e.g. React)" value={skill} onChange={(e) => (setSkill(e.target.value), setPage(1))} />
        </div>
      </Card>

      {list.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-44" />
          ))}
        </div>
      ) : list.isError ? (
        <ErrorState message={errorMessage(list.error)} onRetry={() => list.refetch()} />
      ) : !list.data?.items.length ? (
        <Card>
          <EmptyState
            icon={<FolderKanban className="h-6 w-6" />}
            title={dq || dskill ? "No projects match your filters" : "No portfolio projects yet"}
            description="Add projects you've genuinely worked on. BidGenie uses them as evidence when scoring jobs and writing proposals."
            action={<Button onClick={() => setEditing("new")}>Add your first project</Button>}
          />
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {list.data.items.map((p) => (
              <Card key={p.id} className="flex flex-col p-5">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold leading-snug text-ink">{p.title}</h3>
                  <EmbeddingBadge p={p} />
                </div>
                <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-muted">
                  {p.category && <span>{p.category}</span>}
                  {p.role && <span>· {p.role}</span>}
                  <DemoBadge show={p.is_demo} />
                </div>
                <p className="mt-3 line-clamp-3 text-sm text-ink-soft">{p.description}</p>
                <div className="mt-3">
                  <SkillChips skills={p.skills.slice(0, 6)} tone="brand" />
                </div>
                <div className="mt-auto flex items-center justify-between gap-2 pt-4">
                  {p.url ? (
                    <a href={p.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-brand-600 hover:underline">
                      View <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  ) : (
                    <span />
                  )}
                  <div className="flex gap-1">
                    <Button size="sm" variant="ghost" aria-label={`Edit ${p.title}`} onClick={() => setEditing(p)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="ghost" aria-label={`Delete ${p.title}`} onClick={() => setDeleting(p)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
          <Pagination page={page} pages={list.data.pages} onChange={setPage} />
        </>
      )}

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "Add portfolio project" : "Edit project"} size="lg">
        {editing !== null && <PortfolioForm project={editing === "new" ? undefined : editing} onDone={() => setEditing(null)} />}
      </Modal>
      <ConfirmDialog
        open={!!deleting}
        title="Delete project?"
        message={`“${deleting?.title}” will be deleted and removed from semantic search.`}
        confirmLabel="Delete"
        danger
        loading={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting.id)}
        onCancel={() => setDeleting(null)}
      />
    </>
  );
}
