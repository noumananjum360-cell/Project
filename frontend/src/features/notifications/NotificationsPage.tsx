import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Bell } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { formatDate } from "@/components/domain";
import { useToast } from "@/components/ui/overlays";
import { Button, Card, EmptyState, ErrorState, PageHeader, Pagination, Skeleton } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api";
import { notificationsApi } from "@/services";
import type { Notification } from "@/types/api";

export default function NotificationsPage() {
  const [page, setPage] = useState(1);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const list = useQuery({
    queryKey: ["notifications", page, unreadOnly],
    queryFn: () => notificationsApi.list({ page, unread_only: unreadOnly }),
    placeholderData: keepPreviousData,
  });
  const readAll = useMutation({
    mutationFn: notificationsApi.readAll,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const open = async (n: Notification) => {
    if (!n.read_at) {
      try {
        await notificationsApi.read(n.id);
        qc.invalidateQueries({ queryKey: ["notifications"] });
      } catch (e) {
        toast.error(errorMessage(e));
      }
    }
    if (n.link) navigate(n.link);
  };

  return (
    <>
      <PageHeader
        title="Notifications"
        description="High-fit jobs and follow-up reminders you scheduled."
        actions={
          <>
            <Button variant="outline" aria-pressed={unreadOnly} onClick={() => (setUnreadOnly((u) => !u), setPage(1))}>
              {unreadOnly ? "Show all" : "Unread only"}
            </Button>
            <Button variant="secondary" loading={readAll.isPending} onClick={() => readAll.mutate()} disabled={!list.data?.unread}>
              Mark all read
            </Button>
          </>
        }
      />
      {list.isLoading ? (
        <Skeleton className="h-48" />
      ) : list.isError ? (
        <ErrorState message={errorMessage(list.error)} onRetry={() => list.refetch()} />
      ) : !list.data?.items.length ? (
        <Card>
          <EmptyState icon={<Bell className="h-6 w-6" />} title="You're all caught up" description="Set your Fit Score threshold in Settings to be notified about high-fit jobs." />
        </Card>
      ) : (
        <Card className="divide-y divide-line">
          {list.data.items.map((n) => (
            <button key={n.id} onClick={() => open(n)} className={clsx("block w-full px-5 py-4 text-left hover:bg-slate-50", !n.read_at && "bg-brand-50/40")}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className={clsx("text-sm text-ink", !n.read_at && "font-semibold")}>{n.title}</p>
                  {n.body && <p className="mt-0.5 text-sm text-muted">{n.body}</p>}
                </div>
                <span className="shrink-0 text-xs text-muted">{formatDate(n.created_at, true)}</span>
              </div>
            </button>
          ))}
        </Card>
      )}
      {list.data && <Pagination page={page} pages={list.data.pages} onChange={setPage} />}
    </>
  );
}
