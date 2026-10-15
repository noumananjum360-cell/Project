import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Check } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, ErrorState, Notice, Spinner } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/overlays";
import { useAuth } from "@/features/auth/AuthProvider";
import { PortfolioForm } from "@/features/portfolio/PortfolioPage";
import { errorMessage } from "@/lib/api";
import { authApi, profileApi } from "@/services";
import { ProfileForm } from "./ProfileForm";
import { ResumePanel } from "./ResumePanel";

const STEPS = ["Resume (optional)", "Profile", "First portfolio project", "Done"];

export default function OnboardingPage() {
  const [step, setStep] = useState(0);
  const [added, setAdded] = useState(0);
  const navigate = useNavigate();
  const toast = useToast();
  const { setUser } = useAuth();
  const profile = useQuery({ queryKey: ["profile"], queryFn: profileApi.get });
  const finish = useMutation({
    mutationFn: () => authApi.updateMe({ onboarding_completed: true }),
    onSuccess: (u) => {
      setUser(u);
      navigate("/dashboard", { replace: true });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold">Set up BidGenie</h1>
      <p className="mt-1 text-sm text-muted">A few minutes now makes every Fit Score and proposal more accurate.</p>
      <ol className="my-6 grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Progress">
        {STEPS.map((s, i) => (
          <li
            key={s}
            aria-current={i === step ? "step" : undefined}
            className={clsx(
              "flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium",
              i === step ? "border-brand-500 bg-brand-50 text-brand-700" : i < step ? "border-line text-good" : "border-line text-muted",
            )}
          >
            {i < step ? <Check className="h-3.5 w-3.5" /> : <span>{i + 1}.</span>} {s}
          </li>
        ))}
      </ol>

      {step === 0 && (
        <div className="space-y-4">
          <ResumePanel />
          <div className="flex justify-end">
            <Button onClick={() => setStep(1)}>Continue</Button>
          </div>
        </div>
      )}
      {step === 1 && (
        <Card className="p-5">
          {profile.isLoading ? (
            <Spinner />
          ) : profile.isError ? (
            <ErrorState message={errorMessage(profile.error)} onRetry={() => profile.refetch()} />
          ) : (
            <ProfileForm key={profile.data!.updated_at} profile={profile.data!} compact submitLabel="Save and continue" onSaved={() => setStep(2)} />
          )}
          <div className="mt-2">
            <Button variant="ghost" onClick={() => setStep(0)}>
              ← Back
            </Button>
          </div>
        </Card>
      )}
      {step === 2 && (
        <Card className="space-y-4 p-5">
          <Notice tone="neutral">Add a real project you worked on. You can add more later from the Portfolio page.</Notice>
          {added > 0 && <Notice tone="good">{added} project{added > 1 ? "s" : ""} added.</Notice>}
          <PortfolioForm key={added} onDone={() => setAdded((n) => n + 1)} />
          <div className="flex justify-between">
            <Button variant="ghost" onClick={() => setStep(1)}>
              ← Back
            </Button>
            <Button variant={added ? "primary" : "outline"} onClick={() => setStep(3)}>
              {added ? "Continue" : "Skip for now"}
            </Button>
          </div>
        </Card>
      )}
      {step === 3 && (
        <Card className="p-6 text-center">
          <h2 className="text-lg font-semibold">You're ready</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted">
            Import a job (paste it, upload a CSV, or use the browser extension) and run an analysis to see your Fit Score.
          </p>
          <Button className="mt-5" loading={finish.isPending} onClick={() => finish.mutate()}>
            Go to dashboard
          </Button>
        </Card>
      )}
    </div>
  );
}
