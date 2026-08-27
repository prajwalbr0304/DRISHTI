import { Link, useSearchParams } from "react-router-dom";
import { Cpu, Fingerprint, Gauge, LineChart, Lock, Radar, Scale, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { useLanguage } from "@/providers/LanguageProvider";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { ExportViewButton, PrintHeader } from "@/components/common/PrintExport";
import { TrendsMode } from "@/routes/analytics/modes/TrendsMode";
import { PatternsMode } from "@/routes/analytics/modes/PatternsMode";
import { SocioMode } from "@/routes/analytics/modes/SocioMode";
import { ForecastsMode } from "@/routes/analytics/modes/ForecastsMode";
import { WorkloadMode } from "@/routes/analytics/modes/WorkloadMode";
import { ExplainabilityMode } from "@/routes/analytics/modes/ExplainabilityMode";

/* ============================================================================
   Analytics & Forecasting (doc 01 §4.6) — dashboards for reading trends, not
   chasing a single case. Sub-nav switches the intent over shared, cited widgets:
     Trends · Crime Patterns · Socio-Economic · Forecasts · Model Explainability
   Every panel carries provenance and an "Explain this" route into Ask DRISHTI.
   An aggregate-only seat gets the aggregate turf; Crime Patterns (individual
   cases) is gated out for it, as link-level views are elsewhere.
   ========================================================================== */

type Mode = "trends" | "patterns" | "socio" | "forecasts" | "workload" | "explain";

const MODES: { key: Mode; label: string; icon: React.ElementType; aggregate: boolean }[] = [
  { key: "trends", label: "Trends", icon: LineChart, aggregate: true },
  { key: "patterns", label: "Crime Patterns", icon: Fingerprint, aggregate: false },
  { key: "socio", label: "Socio-Economic", icon: Scale, aggregate: true },
  { key: "forecasts", label: "Forecasts", icon: Radar, aggregate: true },
  { key: "workload", label: "Case-Review Workload", icon: Gauge, aggregate: true },
  { key: "explain", label: "Model Explainability", icon: Cpu, aggregate: true },
];

export function Analytics() {
  const { role } = useRole();
  const { t } = useLanguage();
  const [sp, setSp] = useSearchParams();
  // Aggregate-only seats see only the aggregate modes. INTERIM: none are.
  const aggregateOnly = !roleCan(role, "case_read");

  const allowed = MODES.filter((m) => !aggregateOnly || m.aggregate);
  const requested = (sp.get("mode") as Mode) ?? "trends";
  const mode: Mode = allowed.some((m) => m.key === requested) ? requested : "trends";

  const setMode = (m: Mode) => {
    const next = new URLSearchParams(sp);
    next.set("mode", m);
    setSp(next, { replace: true });
  };

  const gatedAggregateOnly = aggregateOnly && requested === "patterns";

  return (
    <div>
      <PrintHeader title="Analytics & Forecasting" />
      <PageHeader
        title="Analytics & Forecasting"
        description="Trends, crime patterns, socio-economic signal, forecasts and model explainability."
        actions={
          <div className="flex items-center gap-2">
            <Link to="/governance"
              className="inline-flex items-center gap-1.5 rounded-control border border-hairline px-2.5 py-1.5 text-12 font-medium text-content-dim transition-colors hover:text-content">
              <ShieldCheck className="size-3.5" /> {t("Model governance")}
            </Link>
            <ExportViewButton />
          </div>
        }
      />

      {/* Mode sub-nav */}
      <div className="mb-4 flex flex-wrap gap-1 border-b border-hairline">
        {allowed.map((m) => {
          const Icon = m.icon;
          const active = mode === m.key;
          return (
            <button
              key={m.key}
              type="button"
              onClick={() => setMode(m.key)}
              className={cn(
                "flex items-center gap-2 border-b-2 px-3 py-2 text-13 font-medium transition-colors",
                active
                  ? "border-primary text-content"
                  : "border-transparent text-content-dim hover:text-content",
              )}
            >
              <Icon className="size-4" />
              {t(m.label)}
            </button>
          );
        })}
      </div>

      {gatedAggregateOnly ? (
        <EmptyState
          icon={Lock}
          title="Not available for this role"
          description="Crime-pattern detections resolve to individual FIRs. This role works with aggregate views only — see Trends, Socio-Economic and Forecasts."
        />
      ) : (
        <>
          {mode === "trends" && <TrendsMode />}
          {mode === "patterns" && <PatternsMode />}
          {mode === "socio" && <SocioMode />}
          {mode === "forecasts" && <ForecastsMode />}
          {mode === "workload" && <WorkloadMode />}
          {mode === "explain" && <ExplainabilityMode />}
        </>
      )}
    </div>
  );
}
