import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { TagInput } from "@/components/domain";
import { Button, Field, Input, Select, Textarea } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/overlays";
import { errorMessage } from "@/lib/api";
import { profileApi } from "@/services";
import type { Profile } from "@/types/api";

const money = z
  .string()
  .trim()
  .refine((v) => v === "" || (/^\d+(\.\d{1,2})?$/.test(v) && Number(v) >= 0), "Enter a positive amount (max 2 decimals)");

export const profileSchema = z.object({
  full_name: z.string().trim().max(200),
  headline: z.string().trim().max(300),
  overview: z.string().trim().max(5000),
  primary_skills: z.array(z.string()).max(40),
  additional_skills: z.array(z.string()).max(60),
  years_experience: z
    .string()
    .trim()
    .refine((v) => v === "" || (/^\d+$/.test(v) && Number(v) <= 70), "Enter whole years (0–70)"),
  hourly_rate: money,
  currency: z.string().regex(/^[A-Z]{3}$/, "Use a 3-letter currency code"),
  min_budget: money,
  preferred_categories: z.array(z.string()).max(30),
  preferred_project_types: z.array(z.string()).max(30),
  preferred_client_traits: z.array(z.string()).max(30),
  proposal_tone: z.enum(["professional", "friendly", "confident", "concise", "technical"]),
  proposal_length: z.enum(["short", "standard", "detailed"]),
  languages: z.array(z.string()).max(30),
  timezone: z.string().trim().max(64),
  availability: z.string().trim().max(300),
});
export type ProfileValues = z.infer<typeof profileSchema>;

export function toFormValues(p: Profile): ProfileValues {
  return {
    full_name: p.full_name ?? "",
    headline: p.headline ?? "",
    overview: p.overview ?? "",
    primary_skills: p.primary_skills,
    additional_skills: p.additional_skills,
    years_experience: p.years_experience?.toString() ?? "",
    hourly_rate: p.hourly_rate ?? "",
    currency: p.currency,
    min_budget: p.min_budget ?? "",
    preferred_categories: p.preferred_categories,
    preferred_project_types: p.preferred_project_types,
    preferred_client_traits: p.preferred_client_traits,
    proposal_tone: p.proposal_tone,
    proposal_length: p.proposal_length,
    languages: p.languages,
    timezone: p.timezone ?? "",
    availability: p.availability ?? "",
  };
}

export function toPayload(v: ProfileValues): Partial<Profile> {
  const nul = (s: string) => (s === "" ? null : s);
  return {
    ...v,
    full_name: nul(v.full_name),
    headline: nul(v.headline),
    overview: nul(v.overview),
    years_experience: v.years_experience === "" ? null : Number(v.years_experience),
    hourly_rate: nul(v.hourly_rate),
    min_budget: nul(v.min_budget),
    timezone: nul(v.timezone),
    availability: nul(v.availability),
  };
}

export function ProfileForm({
  profile,
  onSaved,
  submitLabel = "Save profile",
  compact = false,
}: {
  profile: Profile;
  onSaved?: (p: Profile) => void;
  submitLabel?: string;
  compact?: boolean;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const { register, handleSubmit, control, formState, reset } = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: toFormValues(profile),
  });
  const save = useMutation({
    mutationFn: (v: ProfileValues) => profileApi.update(toPayload(v)),
    onSuccess: (p) => {
      qc.setQueryData(["profile"], p);
      reset(toFormValues(p));
      toast.success("Profile saved.");
      onSaved?.(p);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const err = formState.errors;
  const tags = (name: "primary_skills" | "additional_skills" | "preferred_categories" | "preferred_project_types" | "preferred_client_traits" | "languages", label: string, hint?: string) => (
    <Field label={label} htmlFor={name} hint={hint ?? "Press Enter or comma to add."}>
      <Controller control={control} name={name} render={({ field }) => <TagInput id={name} value={field.value} onChange={field.onChange} />} />
    </Field>
  );

  return (
    <form onSubmit={handleSubmit((v) => save.mutate(v))} className="space-y-6" noValidate>
      <section className="grid gap-4 sm:grid-cols-2">
        <Field label="Full name" htmlFor="full_name" error={err.full_name?.message}>
          <Input id="full_name" {...register("full_name")} />
        </Field>
        <Field label="Professional headline" htmlFor="headline" error={err.headline?.message}>
          <Input id="headline" placeholder="e.g. Full-stack developer (React, FastAPI)" {...register("headline")} />
        </Field>
        <Field label="Professional overview" htmlFor="overview" className="sm:col-span-2" error={err.overview?.message} hint="Only include facts you can stand behind — proposals reuse this text.">
          <Textarea id="overview" rows={compact ? 3 : 5} {...register("overview")} />
        </Field>
        {tags("primary_skills", "Primary skills", "Your strongest, verifiable skills. Used for Fit Scores.")}
        {tags("additional_skills", "Additional skills")}
      </section>

      <section className="grid gap-4 sm:grid-cols-4">
        <Field label="Years of experience" htmlFor="years_experience" error={err.years_experience?.message}>
          <Input id="years_experience" inputMode="numeric" {...register("years_experience")} />
        </Field>
        <Field label="Hourly rate" htmlFor="hourly_rate" error={err.hourly_rate?.message}>
          <Input id="hourly_rate" inputMode="decimal" {...register("hourly_rate")} />
        </Field>
        <Field label="Minimum fixed budget" htmlFor="min_budget" error={err.min_budget?.message}>
          <Input id="min_budget" inputMode="decimal" {...register("min_budget")} />
        </Field>
        <Field label="Currency" htmlFor="currency" error={err.currency?.message}>
          <Input id="currency" maxLength={3} {...register("currency", { setValueAs: (v: string) => v.toUpperCase() })} />
        </Field>
      </section>

      {!compact && (
        <>
          <section className="grid gap-4 sm:grid-cols-2">
            {tags("preferred_categories", "Preferred job categories")}
            {tags("preferred_project_types", "Preferred project types", "e.g. long-term, fixed-price, MVP builds")}
            {tags("preferred_client_traits", "Preferred client characteristics", "e.g. payment verified, clear scope")}
            {tags("languages", "Languages")}
          </section>
          <section className="grid gap-4 sm:grid-cols-4">
            <Field label="Proposal tone" htmlFor="proposal_tone">
              <Select id="proposal_tone" {...register("proposal_tone")}>
                {["professional", "friendly", "confident", "concise", "technical"].map((t) => (
                  <option key={t} value={t}>
                    {t[0].toUpperCase() + t.slice(1)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Proposal length" htmlFor="proposal_length">
              <Select id="proposal_length" {...register("proposal_length")}>
                <option value="short">Short</option>
                <option value="standard">Standard</option>
                <option value="detailed">Detailed</option>
              </Select>
            </Field>
            <Field label="Time zone" htmlFor="timezone" error={err.timezone?.message}>
              <Input id="timezone" placeholder="e.g. Europe/London" {...register("timezone")} />
            </Field>
            <Field label="Availability" htmlFor="availability" error={err.availability?.message}>
              <Input id="availability" placeholder="e.g. 30 hrs/week" {...register("availability")} />
            </Field>
          </section>
        </>
      )}
      <div className="flex justify-end">
        <Button type="submit" loading={save.isPending}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
