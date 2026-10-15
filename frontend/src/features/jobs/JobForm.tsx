import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { TagInput } from "@/components/domain";
import { Button, Field, Input, Select, Textarea } from "@/components/ui/primitives";
import type { Job, JobInput } from "@/types/api";

const money = z
  .string()
  .trim()
  .refine((v) => v === "" || (/^\d+(\.\d{1,2})?$/.test(v) && Number(v) >= 0), "Enter a positive amount");

export const jobSchema = z
  .object({
    title: z.string().trim().min(3, "Title is required").max(300),
    description: z.string().trim().min(20, "Paste at least 20 characters of the description").max(20000),
    budget_min: money,
    budget_max: money,
    currency: z.string().regex(/^[A-Z]{3}$/, "3-letter code"),
    job_type: z.enum(["hourly", "fixed", "unknown"]),
    experience_level: z.enum(["entry", "intermediate", "expert", "unknown"]),
    required_skills: z.array(z.string()).max(40),
    url: z
      .string()
      .trim()
      .refine((v) => v === "" || /^https?:\/\/\S+$/i.test(v), "Use a full http(s):// URL"),
    posted_at: z.string(),
    proposals_info: z.string().trim().max(200),
    payment_verified: z.enum(["", "yes", "no"]),
    client_country: z.string().trim().max(100),
    client_rating: z
      .string()
      .trim()
      .refine((v) => v === "" || (Number(v) >= 0 && Number(v) <= 5), "0–5"),
    notes: z.string().trim().max(5000),
  })
  .refine((v) => !v.budget_min || !v.budget_max || Number(v.budget_min) <= Number(v.budget_max), {
    path: ["budget_max"],
    message: "Max must be ≥ min",
  });
export type JobValues = z.infer<typeof jobSchema>;

export function jobToValues(j?: Partial<Job | JobInput>): JobValues {
  const ci = (j?.client_info ?? {}) as Job["client_info"];
  return {
    title: j?.title ?? "",
    description: j?.description ?? "",
    budget_min: j?.budget_min ?? "",
    budget_max: j?.budget_max ?? "",
    currency: j?.currency ?? "USD",
    job_type: j?.job_type ?? "unknown",
    experience_level: j?.experience_level ?? "unknown",
    required_skills: j?.required_skills ?? [],
    url: j?.url ?? "",
    posted_at: j?.posted_at ? j.posted_at.slice(0, 10) : "",
    proposals_info: j?.proposals_info ?? "",
    payment_verified: ci.payment_verified === true ? "yes" : ci.payment_verified === false ? "no" : "",
    client_country: ci.country ?? "",
    client_rating: ci.rating?.toString() ?? "",
    notes: j?.notes ?? "",
  };
}

export function valuesToJob(v: JobValues): JobInput {
  const n = (s: string) => (s === "" ? null : s);
  const client = {
    payment_verified: v.payment_verified === "" ? null : v.payment_verified === "yes",
    country: n(v.client_country),
    rating: v.client_rating === "" ? null : Number(v.client_rating),
  };
  const hasClient = Object.values(client).some((x) => x !== null);
  return {
    title: v.title,
    description: v.description,
    budget_min: n(v.budget_min),
    budget_max: n(v.budget_max),
    currency: v.currency,
    job_type: v.job_type,
    experience_level: v.experience_level,
    required_skills: v.required_skills,
    url: n(v.url),
    posted_at: v.posted_at ? new Date(v.posted_at).toISOString() : null,
    proposals_info: n(v.proposals_info),
    client_info: hasClient ? client : null,
    notes: n(v.notes),
  };
}

export function JobForm({
  initial,
  submitLabel,
  loading,
  onSubmit,
}: {
  initial?: Partial<Job | JobInput>;
  submitLabel: string;
  loading?: boolean;
  onSubmit: (v: JobInput) => void;
}) {
  const { register, handleSubmit, control, formState } = useForm<JobValues>({
    resolver: zodResolver(jobSchema),
    defaultValues: jobToValues(initial),
  });
  const e = formState.errors;
  return (
    <form onSubmit={handleSubmit((v) => onSubmit(valuesToJob(v)))} className="grid gap-4 sm:grid-cols-4" noValidate>
      <Field label="Job title" htmlFor="job-title" error={e.title?.message} className="sm:col-span-4">
        <Input id="job-title" {...register("title")} invalid={!!e.title} />
      </Field>
      <Field label="Job description" htmlFor="job-desc" error={e.description?.message} className="sm:col-span-4">
        <Textarea id="job-desc" rows={8} {...register("description")} invalid={!!e.description} />
      </Field>
      <Field label="Required skills" htmlFor="job-skills" className="sm:col-span-4" hint="If left empty, skills are inferred from the description (and marked as inferred).">
        <Controller control={control} name="required_skills" render={({ field }) => <TagInput id="job-skills" value={field.value} onChange={field.onChange} />} />
      </Field>
      <Field label="Job type" htmlFor="job-type">
        <Select id="job-type" {...register("job_type")}>
          <option value="unknown">Unknown</option>
          <option value="hourly">Hourly</option>
          <option value="fixed">Fixed price</option>
        </Select>
      </Field>
      <Field label="Budget min" htmlFor="job-bmin" error={e.budget_min?.message}>
        <Input id="job-bmin" inputMode="decimal" {...register("budget_min")} />
      </Field>
      <Field label="Budget max" htmlFor="job-bmax" error={e.budget_max?.message}>
        <Input id="job-bmax" inputMode="decimal" {...register("budget_max")} />
      </Field>
      <Field label="Currency" htmlFor="job-cur" error={e.currency?.message}>
        <Input id="job-cur" maxLength={3} {...register("currency", { setValueAs: (v: string) => v.toUpperCase() })} />
      </Field>
      <Field label="Experience level" htmlFor="job-level">
        <Select id="job-level" {...register("experience_level")}>
          <option value="unknown">Unknown</option>
          <option value="entry">Entry</option>
          <option value="intermediate">Intermediate</option>
          <option value="expert">Expert</option>
        </Select>
      </Field>
      <Field label="Posted on" htmlFor="job-posted">
        <Input id="job-posted" type="date" {...register("posted_at")} />
      </Field>
      <Field label="Job URL" htmlFor="job-url" error={e.url?.message} className="sm:col-span-2">
        <Input id="job-url" placeholder="https://" {...register("url")} />
      </Field>
      <Field label="Payment verified?" htmlFor="job-pv">
        <Select id="job-pv" {...register("payment_verified")}>
          <option value="">Unknown</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </Select>
      </Field>
      <Field label="Client rating (0–5)" htmlFor="job-rating" error={e.client_rating?.message}>
        <Input id="job-rating" inputMode="decimal" {...register("client_rating")} />
      </Field>
      <Field label="Client country" htmlFor="job-country">
        <Input id="job-country" {...register("client_country")} />
      </Field>
      <Field label="Proposals / applicants" htmlFor="job-props">
        <Input id="job-props" placeholder="e.g. 10 to 15" {...register("proposals_info")} />
      </Field>
      <Field label="Your notes" htmlFor="job-notes" className="sm:col-span-4">
        <Textarea id="job-notes" rows={2} {...register("notes")} />
      </Field>
      <div className="flex justify-end sm:col-span-4">
        <Button type="submit" loading={loading}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
