import { useCallback, useMemo } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BookOpen,
  Clock,
  FileText,
  Gavel,
  GitBranch,
  Landmark,
  Lock,
  MessageSquareText,
  Compass,
  Network,
  Package,
  Paperclip,
  Scale,
  Smartphone,
  Sparkles,
  UserCheck,
  Users,
  Zap,
} from "lucide-react";
import { api } from "@/api";
import { ApiError, errorMessage } from "@/api/contracts";
import { cn } from "@/lib/utils";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { PageHeader } from "@/components/common/PageHeader";
import { SendToBoard } from "@/components/board/SendToBoard";

import { OverviewPage } from "@/routes/cases/subpages/OverviewPage";
import { TimelinePage } from "@/routes/cases/subpages/TimelinePage";
import { ComplainantPage, VictimsPage, AccusedPage } from "@/routes/cases/subpages/PeoplePage";
import { SectionsPage } from "@/routes/cases/subpages/SectionsPage";
import { ArrestsPage } from "@/routes/cases/subpages/ArrestsPage";
import { ChargesheetPage } from "@/routes/cases/subpages/ChargesheetPage";
import { NetworkPage } from "@/routes/cases/subpages/NetworkPage";
import { SimilarPage } from "@/routes/cases/subpages/SimilarPage";
import { SummaryPage } from "@/routes/cases/subpages/SummaryPage";
import { LeadsPage } from "@/routes/cases/subpages/LeadsPage";
import { AssistantPage } from "@/routes/cases/subpages/AssistantPage";
import { EvidencePage } from "@/routes/cases/subpages/EvidencePage";
import { StatementsPage } from "@/routes/cases/subpages/StatementsPage";
import { PropertyPage } from "@/routes/cases/subpages/PropertyPage";
import { CourtLifecyclePage } from "@/routes/cases/subpages/CourtLifecyclePage";
import { DigitalPage } from "@/routes/cases/subpages/DigitalPage";

/* ============================================================================
   Case file shell (doc 01 §4.2): AWS-style object page with a left sub-nav.
   A single /cases/{id}/detail fetch powers the detail sub-pages; async sub-pages
   (similar, summary, leads, network, evidence) fetch independently. A role
   without the case_read capability is blocked with an explicit state.
   ========================================================================== */

interface SubNavItem {
  key: string;
  label: string;
  icon: React.ElementType;
}

const SUB_NAV: SubNavItem[] = [
  { key: "overview", label: "Overview", icon: BookOpen },
  { key: "timeline", label: "Timeline", icon: Clock },
  { key: "complainant", label: "Complainant", icon: Users },
  { key: "victims", label: "Victims", icon: Users },
  { key: "accused", label: "Accused", icon: Users },
  { key: "sections", label: "Acts & Sections", icon: Scale },
  { key: "arrests", label: "Arrests", icon: UserCheck },
  { key: "chargesheet", label: "Chargesheet", icon: Gavel },
  { key: "evidence", label: "Evidence", icon: Paperclip },
  { key: "statements", label: "Statements", icon: MessageSquareText },
  { key: "property", label: "Property & seizures", icon: Package },
  { key: "digital", label: "Digital & financial", icon: Smartphone },
  { key: "court", label: "Court & lifecycle", icon: Landmark },
  { key: "network", label: "Network", icon: Network },
  { key: "similar", label: "Similar cases", icon: GitBranch },
  { key: "summary", label: "AI Summary", icon: Sparkles },
  { key: "leads", label: "Leads", icon: Zap },
  { key: "assistant", label: "Investigation assistant", icon: Compass },
];

export function CaseFile() {
  const { role } = useRole();
  const navigate = useNavigate();
  const { caseId: rawId } = useParams<{ caseId: string }>();
  const caseId = Number(rawId);
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") ?? "overview";

  const goTo = useCallback(
    (key: string) => setSearchParams({ tab: key }, { replace: true }),
    [setSearchParams],
  );

  // Hooks must run unconditionally and in a stable order (React Rules of
  // Hooks), so this query is declared BEFORE the no-access early-return
  // below; it is simply disabled without the capability (who is blocked anyway).
  const q = useQuery({
    queryKey: ["cases", "detail", caseId],
    queryFn: ({ signal }) => api.cases.detail(caseId, signal),
    enabled: roleCan(role, "case_read") && Number.isFinite(caseId) && caseId > 0,
  });

  // Full-file capability block.
  if (!roleCan(role, "case_read")) {
    return (
      <div>
        <PageHeader title="Case file" />
        <EmptyState
          icon={Lock}
          title="Not available for this role"
          description="Individual case files contain personal data and are not accessible to this role. This role sees aggregate-only district views."
        />
      </div>
    );
  }

  if (q.error) {
    const is404 = q.error instanceof ApiError && q.error.status === 404;
    return (
      <EmptyState
        icon={is404 ? FileText : AlertTriangle}
        title={is404 ? "Case not found" : "Couldn't load case"}
        description={errorMessage(q.error)}
        action={
          <Button variant="outline" size="sm" onClick={() => navigate("/cases")}>
            Back to explorer
          </Button>
        }
      />
    );
  }

  const detail = q.data;
  const crimeNo = detail?.core.crime_no ?? `Case ${caseId}`;

  return (
    <div className="flex gap-4">
      {/* Sub-nav rail */}
      <aside className="hidden w-subnav shrink-0 md:block">
        <ScrollArea className="h-[calc(100vh-11rem)]">
          <nav className="space-y-0.5 pr-2">
            {SUB_NAV.map((item) => {
              const Icon = item.icon;
              const active = tab === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => goTo(item.key)}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-control px-2.5 py-2 text-13 font-medium transition-colors",
                    active
                      ? "bg-surface-2 text-content"
                      : "text-content-dim hover:bg-surface-2/60 hover:text-content",
                  )}
                >
                  <Icon className={cn("size-4 shrink-0", active && "text-primary")} />
                  <span className="truncate">{item.label}</span>
                </button>
              );
            })}
          </nav>
        </ScrollArea>
      </aside>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <PageHeader
          title={q.isLoading ? <Skeleton className="h-6 w-64" /> : crimeNo}
          description={
            detail
              ? [detail.core.crime_group, detail.core.district, detail.core.status].filter(Boolean).join(" · ")
              : undefined
          }
          actions={
            detail ? (
              <SendToBoard target={{ refTable: "CaseMaster", refId: caseId, nodeKind: "case", label: crimeNo }} />
            ) : undefined
          }
        />

        {detail && (detail.notices?.length ?? 0) > 0 && (
          <div className="mb-4 space-y-2" aria-label="Case safeguards">
            {detail.notices?.map((notice) => {
              const NoticeIcon = notice.severity === "warning" ? AlertTriangle : BookOpen;
              return (
                <div
                  key={notice.code}
                  className={cn(
                    "flex items-start gap-2 rounded-card border px-3 py-2 text-12",
                    notice.severity === "warning"
                      ? "border-severity-medium/40 bg-severity-medium/5 text-content"
                      : "border-hairline bg-surface-2/40 text-content-dim",
                  )}
                >
                  <NoticeIcon className="mt-0.5 size-4 shrink-0" />
                  <div>
                    <div className="font-semibold">{notice.title}</div>
                    <p className="mt-0.5 leading-relaxed">{notice.message}</p>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {q.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : detail ? (
          <SubPage tab={tab} caseId={caseId} detail={detail} goTo={goTo} />
        ) : null}
      </div>
    </div>
  );
}

function SubPage({
  tab,
  caseId,
  detail,
  goTo,
}: {
  tab: string;
  caseId: number;
  detail: NonNullable<ReturnType<typeof useQuery<import("@/api/types").CaseDetailResponse>>["data"]>;
  goTo: (t: string) => void;
}) {
  switch (tab) {
    case "overview":
      return <OverviewPage detail={detail} goTo={goTo} />;
    case "timeline":
      return <TimelinePage caseId={caseId} detail={detail} />;
    case "complainant":
      return <ComplainantPage detail={detail} />;
    case "victims":
      return <VictimsPage detail={detail} />;
    case "accused":
      return <AccusedPage detail={detail} />;
    case "sections":
      return <SectionsPage detail={detail} />;
    case "arrests":
      return <ArrestsPage detail={detail} />;
    case "chargesheet":
      return <ChargesheetPage detail={detail} />;
    case "evidence":
      return <EvidencePage caseId={caseId} />;
    case "statements":
      return <StatementsPage caseId={caseId} />;
    case "property":
      return <PropertyPage caseId={caseId} />;
    case "digital":
      return <DigitalPage caseId={caseId} />;
    case "court":
      return <CourtLifecyclePage caseId={caseId} />;
    case "network":
      return <NetworkPage caseId={caseId} />;
    case "similar":
      return <SimilarPage caseId={caseId} />;
    case "summary":
      return <SummaryPage caseId={caseId} />;
    case "leads":
      return <LeadsPage caseId={caseId} />;
    case "assistant":
      return <AssistantPage caseId={caseId} />;
    default:
      return <OverviewPage detail={detail} goTo={goTo} />;
  }
}
