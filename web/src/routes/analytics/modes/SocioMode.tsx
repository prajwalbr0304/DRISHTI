import { useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import { useUIStore } from "@/stores/useUIStore";
import { Widget } from "@/components/widget/Widget";
import { NativeSelect } from "@/components/ui/native-select";
import { SocioNarrativeCard } from "@/components/dashboard/SocioNarrativeCard";
import { CorrelationMatrix } from "@/components/charts/CorrelationMatrix";
import { CorrelationScatter } from "@/components/charts/CorrelationScatter";
import { useSocio } from "@/routes/analytics/useAnalyticsData";

/* Socio-Economic (doc 01 §4.6 / doc 03 §2.10): correlation-matrix heatmap +
   scatter (with fitted line) + a plain-language narrative that ALWAYS carries
   the "correlational, not causal" disclaimer and the k-anonymity suppression
   count. A policymaker's home turf. */
export function SocioMode() {
  const askAbout = useUIStore((s) => s.askAbout);
  const [focus, setFocus] = useState<string>("");
  const [category, setCategory] = useState<string>("");

  const q = useSocio(focus || undefined);
  const data = q.data;

  const effectiveIndicator = focus || data?.focus_indicator || "";

  // scatter series present for the focus indicator; default to the strongest |r|.
  const seriesList = data?.scatter ?? [];
  const strongest = useMemo(
    () => [...seriesList].sort((a, b) => Math.abs(b.r ?? 0) - Math.abs(a.r ?? 0))[0],
    [seriesList],
  );
  const selectedSeries =
    seriesList.find((s) => s.crime_category === category) ?? strongest ?? null;

  const explainSeed =
    `Explain the socio-economic signal: how does ${effectiveIndicator || "the indicator"} correlate ` +
    `with ${selectedSeries?.crime_category ?? "crime"} across districts? Make clear this is ` +
    `correlational, not causal.`;

  const explainItem = {
    label: "Explain this in Ask DRISHTI",
    icon: <Sparkles />,
    onSelect: () => askAbout(explainSeed),
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Narrative */}
        <Widget
          title="Socio-economic read-out"
          contextChip="correlational"
          provenance={data?.result}
          loading={q.isLoading}
          error={q.error}
          onRefresh={() => q.refetch()}
          menuItems={[explainItem]}
          info={
            <p className="text-content-dim">
              District per-capita crime rates correlated against socio-economic indicators. Small-count
              cells are suppressed; correlations are never presented as causation.
            </p>
          }
        >
          {data && <SocioNarrativeCard data={data} />}
        </Widget>

        {/* Scatter for the focus indicator × crime category */}
        <Widget
          className="lg:col-span-2"
          title="Crime vs. indicator"
          contextChip={effectiveIndicator || undefined}
          provenance={data?.result}
          loading={q.isLoading}
          error={q.error}
          empty={!q.isLoading && !q.error && !selectedSeries}
          emptyLabel="No scatter series for this indicator."
          onRefresh={() => q.refetch()}
          menuItems={[explainItem]}
          actions={
            <div className="flex items-center gap-2">
              <NativeSelect
                value={effectiveIndicator}
                onChange={setFocus}
                options={(data?.indicators ?? []).map((i) => ({ value: i, label: i }))}
                placeholder="Indicator"
                aria-label="Focus indicator"
                className="w-40"
              />
              {seriesList.length > 1 && (
                <NativeSelect
                  value={selectedSeries?.crime_category ?? ""}
                  onChange={setCategory}
                  options={seriesList.map((s) => ({ value: s.crime_category, label: s.crime_category }))}
                  placeholder="Crime category"
                  aria-label="Crime category"
                  className="w-40"
                />
              )}
            </div>
          }
        >
          {selectedSeries && <CorrelationScatter series={selectedSeries} />}
        </Widget>
      </div>

      {/* Correlation matrix */}
      <Widget
        title="Correlation matrix"
        contextChip={data ? `${data.crime_categories.length}×${data.indicators.length}` : undefined}
        provenance={data?.result}
        loading={q.isLoading}
        error={q.error}
        empty={!q.isLoading && !q.error && (data?.correlation_matrix.length ?? 0) === 0}
        onRefresh={() => q.refetch()}
        menuItems={[explainItem]}
        info={
          <p className="text-content-dim">
            Pearson r for every crime category × indicator pair. Click a cell to focus the scatter on
            that indicator.
          </p>
        }
      >
        {data && (
          <CorrelationMatrix
            cells={data.correlation_matrix}
            focusIndicator={effectiveIndicator}
            onSelect={(indicator, crimeCategory) => {
              setFocus(indicator);
              setCategory(crimeCategory);
            }}
          />
        )}
      </Widget>
    </div>
  );
}
