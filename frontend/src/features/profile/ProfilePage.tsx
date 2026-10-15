import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { DemoBadge } from "@/components/domain";
import { ConfirmDialog, useToast } from "@/components/ui/overlays";
import { Button, Card, CardHeader, ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api";
import { profileApi } from "@/services";
import { ProfileForm } from "./ProfileForm";
import { ResumePanel } from "./ResumePanel";

export default function ProfilePage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const profile = useQuery({ queryKey: ["profile"], queryFn: profileApi.get });
  const clear = useMutation({
    mutationFn: profileApi.clear,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile"] });
      setConfirm(false);
      toast.success("Profile data cleared.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <PageHeader
        title="Freelancer profile"
        description="Your verified profile is the only source of facts BidGenie uses for scoring and proposals."
        actions={
          <Button variant="outline" onClick={() => setConfirm(true)}>
            Clear profile
          </Button>
        }
      />
      <div className="space-y-6">
        <ResumePanel />
        <Card>
          <CardHeader title={<span className="flex items-center gap-2">Profile details <DemoBadge show={!!profile.data?.is_demo} /></span>} />
          <div className="p-5">
            {profile.isLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-10" />
                <Skeleton className="h-24" />
                <Skeleton className="h-10" />
              </div>
            ) : profile.isError ? (
              <ErrorState message={errorMessage(profile.error)} onRetry={() => profile.refetch()} />
            ) : (
              <ProfileForm key={profile.data!.updated_at} profile={profile.data!} />
            )}
          </div>
        </Card>
      </div>
      <ConfirmDialog
        open={confirm}
        title="Clear profile data?"
        message="All profile fields will be reset. Your account, portfolio, jobs and proposals are not affected."
        confirmLabel="Clear profile"
        danger
        loading={clear.isPending}
        onConfirm={() => clear.mutate()}
        onCancel={() => setConfirm(false)}
      />
    </>
  );
}
