import { useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import { useUIStore } from "@/stores/useUIStore";
import { Widget } from "@/components/widget/Widget";
import { NativeSelect } from "@/components/ui/native-select";
import { SocioNarrativeCard } from "@/components/dashboard/SocioNarrativeCard";
import { IndicatorCrimeCard } from "@/components/dashboard/IndicatorCrimeCard";
import { CorrelationBars } from "@/components/charts/CorrelationBars";
import { CorrelationMatrix } from "@/components/charts/CorrelationMatrix";
import { useSocio } from "@/routes/analytics/useAnalyticsData";
import { defaultCrimeCategory, indicatorsByStrength } from "@/lib/socio";

/* Socio-Economic (doc 01 §4.6 / doc 03 §2.10).

   One box per indicator, each with its own crime-type selector, so all ten
   indicators are readable at once instead of nine of them living as bars behind a
   single scatter. Geography is NOT repeated per box — the workspace already has
   one district selector in the top bar, and each box rings that district inside
   its own state-wide cloud. Above them: the plain-language read-out, which always
   carries the "correlational, not causal" disclaimer and the k-anonymity
   suppression count. Below: the full matrix, for scanning every pairing at once.

   One request feeds the whole page — /analytics/socioeconomic publishes the
   district panel and a fit per cell, so every box builds its own series client-
   side (see lib/socio) rather than re-querying per indicator. */
export function SocioMode() {
  const askAbout = useUIStore((s) => s.askAbout);

  const q = useSocio();
  const data = q.data;

  /* Page-level crime type sets the DEFAULT for every box; a box that has been
     changed individually keeps its own choice. Empty = follow the server's
     narrative category. */
  const [category, setCategory] = useState<string>("");
  const [matrixFocus, setMatrixFocus] = useState<string>("");

  const activeCategory = category || (data ? defaultCrimeCategory(data) : "");

  // Strongest signal first, so the grid opens on the indicators that say
  // something rather than on whatever order the service declared them in.
  const indicators = useMemo(
    () => (data && activeCategory ? indicatorsByStrength(data, activeCategory) : []),
    [data, activeCategory],
  );

  const explainItem = {
    label: "Explain this in Ask DRISHTI",
    icon: <Sparkles />,
    onSelect: () =>
      askAbout(
        `Explain the socio-economic signal: which indicators correlate with per-capita ` +
          `${(activeCategory || "crime").toLowerCase()} across Karnataka districts, and how strongly? ` +
          `Make clear this is correlational, not causal.`,
      ),
  };

  return (
    <div className="space-y-4">
      {/* Plain-language read-out + the honesty footer */}
      <Widget
        title="Socio-economic read-out"
        contextChip="correlational"
        provenance={data?.result}
        loading={q.isLoading}
        error={q.error}
        onRefresh={() => q.refetch()}
        menuItems={[explainItem]}
        actions={
          <NativeSelect
            value={category}
            onChange={setCategory}
            options={(data?.crime_categories ?? []).map((c) => ({ value: c, label: c }))}
            placeholder={activeCategory ? `Auto · ${activeCategory}` : "Crime type"}
            aria-label="Default crime type for every indicator box"
            className="w-56"
          />
        }
        info={
          <div className="space-y-2">
            <p>
              District per-capita crime rates correlated against socio-economic indicators, with r
              for every indicator ranked beside the narrative — the index for the per-indicator boxes
              below. Small-count cells are suppressed; correlations are never presented as causation.
            </p>
            <p>
              The crime type chosen here is the DEFAULT for those boxes; any box you set individually
              keeps its own selection. Geography comes from the district selector in the top bar,
              which rings that district inside each box rather than filtering to it.
            </p>
          </div>
        }
      >
        {data && (
          <div className="grid grid-cols-1 gap-x-5 gap-y-3 lg:grid-cols-12">
            {/* compact: the ranked top-5 list would restate the bars beside it. */}
            <div className="min-w-0 lg:col-span-4">
              <SocioNarrativeCard data={data} compact />
            </div>
            <div className="min-w-0 lg:col-span-8">
              {activeCategory && (
                <CorrelationBars cells={data.correlation_matrix} crimeCategory={activeCategory} />
              )}
            </div>
          </div>
        )}
      </Widget>

      {/* One box per indicator — each owns its crime type and geography */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
        {indicators.map((indicator) => (
          <IndicatorCrimeCard
            key={indicator}
            data={data}
            indicator={indicator}
            defaultCrimeCategory={activeCategory}
            provenance={data?.result}
            loading={q.isLoading}
            error={q.error}
            onRefresh={() => q.refetch()}
            chartHeight={220}
          />
        ))}
      </div>

      {/* Every pairing at once */}
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
            Pearson r for every crime category × indicator pair. Click a cell to make that crime type
            the default for the indicator boxes above.
          </p>
        }
      >
        {data && (
          <CorrelationMatrix
            cells={data.correlation_matrix}
            focusIndicator={matrixFocus}
            onSelect={(indicator, crimeCategory) => {
              setMatrixFocus(indicator);
              setCategory(crimeCategory);
            }}
          />
        )}
      </Widget>
    </div>
  );
}
