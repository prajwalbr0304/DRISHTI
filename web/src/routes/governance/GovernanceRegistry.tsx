import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/common/PageHeader";
import { LabelsPanel, PredictionsPanel, RegistryPanel, SnapshotsPanel } from "./panels";

/* Phase-10 governance workspace: the admin feature/model registry + the
   governed feature-snapshot builder + the prediction job queue (build -> run ->
   review). Predictions are aggregate decision-support only; every result ties
   to an immutable feature snapshot and protected attributes never enter a
   prediction schema. Reads are open; writes are role-gated server-side. */

type Tab = "registry" | "snapshots" | "predictions" | "labels";

const TABS: { id: Tab; label: string }[] = [
  { id: "registry", label: "Registry" },
  { id: "snapshots", label: "Feature snapshots" },
  { id: "predictions", label: "Predictions" },
  { id: "labels", label: "Labels" },
];

export function GovernanceRegistry() {
  const [tab, setTab] = useState<Tab>("registry");
  return (
    <div>
      <PageHeader
        title="Model governance"
        description="Feature definitions, versioned schemas, immutable feature snapshots and governed, reviewable predictions — the safe bridge between verified inputs and any model."
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

      {tab === "registry" && <RegistryPanel />}
      {tab === "snapshots" && <SnapshotsPanel />}
      {tab === "predictions" && <PredictionsPanel />}
      {tab === "labels" && <LabelsPanel />}
    </div>
  );
}
