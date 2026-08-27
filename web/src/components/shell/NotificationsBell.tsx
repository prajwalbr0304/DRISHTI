import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Bell, MapPin } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { AlertFeature, AlertSeverity } from "@/api/types";
import { cn, timeAgo } from "@/lib/utils";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { usePeekStore } from "@/stores/usePeekStore";
import { useLanguage } from "@/providers/LanguageProvider";

/* ============================================================================
   Notifications bell — backed by REAL active geo alerts (no notifications
   endpoint exists, and there are no mocks). The count reflects high/critical
   alerts; the list shows the most recent, each openable in the peek rail.
   ========================================================================== */

const SEV_BADGE: Record<AlertSeverity, BadgeProps["variant"]> = {
  critical: "critical",
  high: "high",
  medium: "medium",
  low: "low",
  info: "neutral",
};

export function NotificationsBell() {
  const push = usePeekStore((s) => s.push);
  const { t } = useLanguage();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["alerts", "bell"],
    queryFn: ({ signal }) => api.geo.alerts({ limit: 50 }, signal),
    refetchInterval: 120_000,
  });

  const alerts = data?.alerts ?? [];
  const urgent = alerts.filter((a) => a.severity === "critical" || a.severity === "high").length;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={t("Active alerts") + ` (${urgent})`}>
          <Bell />
          {urgent > 0 && (
            <span className="absolute right-1 top-1 grid min-w-[16px] place-items-center rounded-full bg-severity-critical px-1 text-[10px] font-semibold leading-4 text-white tnum">
              {urgent > 9 ? "9+" : urgent}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[26rem] p-0">
        <div className="flex items-center justify-between border-b border-hairline px-3 py-2.5">
          <div className="text-13 font-semibold text-content">{t("Active alerts")}</div>
          <Badge variant="neutral" className="tnum">
            {alerts.length}
          </Badge>
        </div>

        <ScrollArea className="h-[min(24rem,70vh)]" type="always">
          <div className="p-1.5">
            {isLoading && (
              <div className="space-y-2 p-2">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            )}

            {error && (
              <div className="flex flex-col items-center gap-2 p-6 text-center">
                <AlertTriangle className="size-5 text-severity-high" />
                <p className="text-12 text-content-dim">{errorMessage(error)}</p>
                <Button variant="outline" size="sm" onClick={() => refetch()}>
                  {t("Retry")}
                </Button>
              </div>
            )}

            {!isLoading && !error && alerts.length === 0 && (
              <p className="p-6 text-center text-13 text-content-dim">{t("No active alerts.")}</p>
            )}

            {!error &&
              alerts.map((a) => <AlertRow key={a.alert_id} alert={a} onOpen={() => openAlert(a, push)} />)}
          </div>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}

function openAlert(a: AlertFeature, push: ReturnType<typeof usePeekStore.getState>["push"]) {
  push({
    kind: "alert",
    id: a.alert_id,
    label: a.title,
    sublabel: a.district_name ?? a.alert_type,
  });
}

function AlertRow({ alert, onOpen }: { alert: AlertFeature; onOpen: () => void }) {
  const { t } = useLanguage();

  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-start gap-2.5 rounded-control px-2.5 py-2 text-left transition-colors hover:bg-surface-2"
    >
      <span className="mt-1 shrink-0">
        <AlertTriangle
          className={cn(
            "size-4",
            alert.severity === "critical" && "text-severity-critical",
            alert.severity === "high" && "text-severity-high",
            alert.severity === "medium" && "text-severity-medium",
            (alert.severity === "low" || alert.severity === "info") && "text-content-dim",
          )}
        />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-start gap-2">
          <span className="text-13 font-medium leading-snug text-content">{alert.title}</span>
          <Badge variant={SEV_BADGE[alert.severity]} className="mt-0.5 shrink-0 capitalize">
            {t(alert.severity)}
          </Badge>
        </span>
        {alert.message && <span className="mt-0.5 block text-12 leading-normal text-content-dim">{alert.message}</span>}
        <span className="mt-1 flex items-center gap-2 text-12 text-content-dim">
          {alert.district_name && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="size-3" />
              {alert.district_name}
            </span>
          )}
          {alert.created_at && <span className="tnum">{timeAgo(alert.created_at)}</span>}
        </span>
      </span>
    </button>
  );
}
