import { useState } from "react";
import { Lock } from "lucide-react";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import {
  AccountsPanel,
  EntityLinksPanel,
  ImportInboxPanel,
  MoneyAlertsPanel,
} from "@/routes/imports/panels";

/* ============================================================================
   Phase 8 workspace: template-driven digital + financial imports.
   Tabs: Import inbox (dry-run/commit/rollback) · Entity-link review ·
   Accounts & transactions · Money alerts. A seat without the capability is
   blocked; financial tabs are additionally permission-gated server-side.
   ========================================================================== */

const TABS = [
  { key: "inbox", label: "Import inbox" },
  { key: "links", label: "Entity-link review" },
  { key: "accounts", label: "Accounts & transactions" },
  { key: "money", label: "Money alerts" },
] as const;

export function ImportsWorkspace() {
  const { role } = useRole();
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("inbox");

  if (!roleCan(role, "imports_review")) {
    return (
      <div>
        <PageHeader title="Digital & financial imports" />
        <EmptyState icon={Lock} title="Not available for this role"
          description="Structured imports and financial data are not accessible to this role, which works with aggregate views only." />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Digital & financial imports"
        description="Template-driven CDR / chat / IP / device / location and bank / account / wallet imports — staged, dry-run, reviewed and committed with provenance."
      />
      <div className="mb-4 flex flex-wrap items-center gap-1">
        {TABS.map((t) => (
          <button key={t.key} type="button" onClick={() => setTab(t.key)}
            className={cn("rounded-control px-2.5 py-1 text-12 font-medium transition-colors",
              tab === t.key ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content")}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "inbox" && <ImportInboxPanel />}
      {tab === "links" && <EntityLinksPanel />}
      {tab === "accounts" && <AccountsPanel />}
      {tab === "money" && <MoneyAlertsPanel />}
    </div>
  );
}
