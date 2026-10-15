import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import { Modal, useToast } from "@/components/ui/overlays";
import { Badge, Button, Card, CardHeader, Field, Input, LinkButton, Notice, PageHeader, Skeleton } from "@/components/ui/primitives";
import { useAuth } from "@/features/auth/AuthProvider";
import { passwordRule } from "@/features/auth/AuthPages";
import { errorMessage } from "@/lib/api";
import { accountApi, authApi, profileApi } from "@/services";
import type { Preferences } from "@/types/api";

function PreferencesCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const prefs = useQuery({ queryKey: ["preferences"], queryFn: profileApi.preferences });
  const [form, setForm] = useState<Preferences | null>(null);
  useEffect(() => {
    if (prefs.data) setForm(prefs.data);
  }, [prefs.data]);
  const save = useMutation({
    mutationFn: (p: Preferences) => profileApi.updatePreferences(p),
    onSuccess: (p) => {
      qc.setQueryData(["preferences"], p);
      toast.success("Preferences saved.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const valid = form && form.fit_score_threshold >= 0 && form.fit_score_threshold <= 100;
  return (
    <Card>
      <CardHeader title="Job alerts & automation" />
      <div className="space-y-4 p-5">
        {!form ? (
          <Skeleton className="h-24" />
        ) : (
          <>
            <Field label="Fit Score notification threshold" htmlFor="threshold" hint="You'll be notified when an analyzed job scores at or above this value." error={valid ? undefined : "Enter 0–100"}>
              <Input
                id="threshold"
                type="number"
                min={0}
                max={100}
                className="max-w-32"
                value={form.fit_score_threshold}
                onChange={(e) => setForm({ ...form, fit_score_threshold: Number(e.target.value) })}
              />
            </Field>
            {(
              [
                ["notify_high_fit_jobs", "Notify me about high-fit jobs"],
                ["notify_follow_ups", "Notify me about follow-up reminders"],
                ["auto_analyze_on_import", "Automatically analyze newly imported jobs (uses AI credits)"],
              ] as const
            ).map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.checked })} />
                {label}
              </label>
            ))}
            <div className="flex justify-end">
              <Button disabled={!valid} loading={save.isPending} onClick={() => save.mutate(form)}>
                Save preferences
              </Button>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}

const pwSchema = z
  .object({ current: z.string().min(1, "Required"), next: passwordRule, confirm: z.string() })
  .refine((v) => v.next === v.confirm, { path: ["confirm"], message: "Passwords do not match" });

function PasswordCard() {
  const toast = useToast();
  const { register, handleSubmit, formState, reset } = useForm<z.infer<typeof pwSchema>>({ resolver: zodResolver(pwSchema) });
  const change = useMutation({
    mutationFn: (v: z.infer<typeof pwSchema>) => authApi.changePassword(v.current, v.next),
    onSuccess: (r) => {
      toast.success(r.message);
      reset();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const e = formState.errors;
  return (
    <Card>
      <CardHeader title="Change password" description="Other signed-in sessions (including the browser extension) will be signed out." />
      <form className="grid gap-4 p-5 sm:grid-cols-3" onSubmit={handleSubmit((v) => change.mutate(v))} noValidate>
        <Field label="Current password" htmlFor="pw-cur" error={e.current?.message}>
          <Input id="pw-cur" type="password" autoComplete="current-password" {...register("current")} />
        </Field>
        <Field label="New password" htmlFor="pw-new" error={e.next?.message}>
          <Input id="pw-new" type="password" autoComplete="new-password" {...register("next")} />
        </Field>
        <Field label="Confirm new password" htmlFor="pw-conf" error={e.confirm?.message}>
          <Input id="pw-conf" type="password" autoComplete="new-password" {...register("confirm")} />
        </Field>
        <div className="flex justify-end sm:col-span-3">
          <Button type="submit" loading={change.isPending}>
            Update password
          </Button>
        </div>
      </form>
    </Card>
  );
}

export default function SettingsPage() {
  const { user, setUser } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [name, setName] = useState(user?.full_name ?? "");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePw, setDeletePw] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState("");

  const saveName = useMutation({
    mutationFn: () => authApi.updateMe({ full_name: name.trim() }),
    onSuccess: (u) => {
      setUser(u);
      toast.success("Account updated.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const resend = useMutation({
    mutationFn: authApi.resendVerification,
    onSuccess: (r) => toast.success(r.message),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const exportData = useMutation({
    mutationFn: accountApi.exportData,
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "bidgenie-export.json";
      a.click();
      URL.revokeObjectURL(url);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: () => accountApi.remove(deletePw),
    onSuccess: () => {
      setUser(null);
      navigate("/", { replace: true });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <PageHeader title="Settings" description="Account, security, notifications and privacy." actions={<LinkButton to="/profile" variant="outline">Edit freelancer profile</LinkButton>} />
      <div className="space-y-6">
        <Card>
          <CardHeader title="Account" />
          <div className="grid gap-4 p-5 sm:grid-cols-2">
            <Field label="Name" htmlFor="acc-name">
              <Input id="acc-name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
            </Field>
            <div className="space-y-1.5">
              <p className="text-sm font-medium text-ink-soft">Email</p>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                {user?.email}
                {user?.email_verified_at ? <Badge tone="good">Verified</Badge> : <Badge tone="warn">Unverified</Badge>}
                {!user?.email_verified_at && (
                  <Button size="sm" variant="ghost" loading={resend.isPending} onClick={() => resend.mutate()}>
                    Resend link
                  </Button>
                )}
              </div>
            </div>
            <div className="flex justify-end sm:col-span-2">
              <Button loading={saveName.isPending} onClick={() => saveName.mutate()} disabled={!name.trim()}>
                Save
              </Button>
            </div>
          </div>
        </Card>
        <PreferencesCard />
        <PasswordCard />
        <Card>
          <CardHeader title="Privacy & data" />
          <div className="space-y-4 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-ink-soft">Download a JSON export of your profile, portfolio, jobs, analyses, proposals and tracker records.</p>
              <Button variant="outline" loading={exportData.isPending} onClick={() => exportData.mutate()}>
                Export my data
              </Button>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
              <p className="text-sm text-ink-soft">Permanently delete your account and all associated data, files and search vectors.</p>
              <Button variant="danger" onClick={() => setDeleteOpen(true)}>
                Delete account
              </Button>
            </div>
          </div>
        </Card>
      </div>
      <Modal
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        title="Delete your account"
        size="sm"
        footer={
          <>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" disabled={!deletePw || deleteConfirm !== "DELETE"} loading={remove.isPending} onClick={() => remove.mutate()}>
              Delete permanently
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Notice tone="bad">This cannot be undone. All your data will be permanently removed.</Notice>
          <Field label="Password" htmlFor="del-pw">
            <Input id="del-pw" type="password" autoComplete="current-password" value={deletePw} onChange={(e) => setDeletePw(e.target.value)} />
          </Field>
          <Field label='Type "DELETE" to confirm' htmlFor="del-confirm">
            <Input id="del-confirm" value={deleteConfirm} onChange={(e) => setDeleteConfirm(e.target.value)} />
          </Field>
        </div>
      </Modal>
    </>
  );
}
