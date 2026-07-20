import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/common/PageHeader";
import {
  AssistantPanel, AuditPanel, IdentityPanel, ModelsPanel, NotificationsPanel, QueuesPanel,
  ReconciliationPanel, ReportsPanel, RetentionPanel, StatusPanel, UsagePanel,
} from "./panels";
import { OrgAccessPanel } from "./OrgAccessPanel";

/* Phase-15 Admin / governance console. Replaces the model-registry-only
   placeholder with the hackathon administration + observability surface:
   status indicators, the Catalyst identity→role authorization matrix, source
   reconciliation, non-destructive retention/legal-hold, model review-due,
   queues, usage/budgets/feature-flags, audit search/export, reports,
   notifications/work and the optional approved-text assistant. Everything is
   synthetic-demo data; writes are role-gated + write-guarded server-side. */

type Tab =
  | "status" | "identity" | "access" | "reconciliation" | "retention" | "models"
  | "queues" | "usage" | "audit" | "reports" | "notifications" | "assistant";

const TABS: { id: Tab; label: string }[] = [
  { id: "status", label: "Status" },
  { id: "identity", label: "Identity & roles" },
  { id: "access", label: "Access & hierarchy" },
  { id: "reconciliation", label: "Reconciliation" },
  { id: "retention", label: "Retention & legal hold" },
  { id: "models", label: "Model review" },
  { id: "queues", label: "Queues" },
  { id: "usage", label: "Usage & flags" },
  { id: "audit", label: "Audit" },
  { id: "reports", label: "Reports" },
  { id: "notifications", label: "Notifications" },
  { id: "assistant", label: "Assistant" },
];

export function AdminConsole() {
  const [tab, setTab] = useState<Tab>("status");
  return (
    <div>
      <PageHeader
        title="Admin & governance"
        description="Hackathon administration, observability, reporting and the optional approved-text assistant — all on synthetic demonstration data."
        actions={<Badge variant="neutral">Synthetic Hackathon Demo</Badge>}
      />

      <div className="mb-4 flex flex-wrap gap-1 border-b border-hairline">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-13 font-medium transition-colors ${
              tab === t.id
                ? "border-primary text-content"
                : "border-transparent text-content-dim hover:text-content"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "status" && <StatusPanel />}
      {tab === "identity" && <IdentityPanel />}
      {tab === "access" && <OrgAccessPanel />}
      {tab === "reconciliation" && <ReconciliationPanel />}
      {tab === "retention" && <RetentionPanel />}
      {tab === "models" && <ModelsPanel />}
      {tab === "queues" && <QueuesPanel />}
      {tab === "usage" && <UsagePanel />}
      {tab === "audit" && <AuditPanel />}
      {tab === "reports" && <ReportsPanel />}
      {tab === "notifications" && <NotificationsPanel />}
      {tab === "assistant" && <AssistantPanel />}
    </div>
  );
}
