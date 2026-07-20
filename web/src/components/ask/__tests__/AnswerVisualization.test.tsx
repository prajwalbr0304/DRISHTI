import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

/* The map stack (maplibre + deck.gl) needs WebGL — stub it in jsdom. Geo
   boundaries are mocked per-test so the choropleth fallback is deterministic. */
const boundaries = vi.fn();
vi.mock("@/api", () => ({ api: { geo: { boundaries: (...a: unknown[]) => boundaries(...a) } } }));
vi.mock("@/components/map/MapCanvas", () => ({
  MapCanvas: () => <div data-testid="map" />,
}));

import { AnswerVisualization } from "@/components/ask/AnswerVisualization";
import type { AskMessage } from "@/stores/useAskStore";
import type { VizSpec } from "@/api/types";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

function baseViz(partial: Partial<VizSpec>): VizSpec {
  return {
    kind: "table",
    title: "Answer",
    dimensions: [],
    measures: [],
    time_field: null,
    geo_field: null,
    source_ids: [],
    as_of: "2024-06-01T09:30:00Z",
    dataset: "synthetic",
    suppressed: 0,
    confidence: 0.82,
    scope_role: "state",
    row_total: 0,
    language: "en",
    accessible_table: { columns: [], row_ref: "rows_preview" },
    ...partial,
  };
}

function msg(partial: Partial<AskMessage>): AskMessage {
  return {
    id: "a1",
    sender: "assistant",
    text: "Here is the answer.",
    createdAt: 0,
    columns: [],
    rowsPreview: [],
    rowCount: 0,
    citedRecordIds: [],
    confidence: 0.82,
    ...partial,
  };
}

describe("AnswerVisualization (Prompt 19 typed viz)", () => {
  beforeEach(() => {
    boundaries.mockReset();
  });

  it("number: shows the big number, its unit, and a data-table toggle", () => {
    const viz = baseViz({
      kind: "number",
      title: "Total FIRs",
      measures: [{ field: "n", label: "FIRs", index: 0, unit: "cases" }],
    });
    wrap(
      <AnswerVisualization
        message={msg({ visualization: viz, columns: ["n"], rowsPreview: [[1234]], rowCount: 1 })}
      />,
    );
    expect(screen.getByText("1,234")).toBeInTheDocument();
    expect(screen.getByText("cases")).toBeInTheDocument();
    // accessible table always present, tucked behind a details toggle for charts
    expect(screen.getByText(/show data table/i)).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("bar: renders and always exposes the accessible data table", () => {
    const viz = baseViz({
      kind: "bar",
      title: "FIRs by district",
      dimensions: [{ field: "district", label: "District", index: 0, role: "dimension" }],
      measures: [{ field: "n", label: "FIRs", index: 1, unit: "" }],
    });
    wrap(
      <AnswerVisualization
        message={msg({
          visualization: viz,
          columns: ["district", "n"],
          rowsPreview: [
            ["Bengaluru", 10],
            ["Mysuru", 5],
          ],
          rowCount: 2,
        })}
      />,
    );
    expect(screen.getByText(/show data table/i)).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("Bengaluru")).toBeInTheDocument();
    expect(within(table).getByText("Mysuru")).toBeInTheDocument();
  });

  it("line: renders a trend and keeps the accessible data table", () => {
    const viz = baseViz({
      kind: "line",
      title: "Monthly trend",
      time_field: "month",
      dimensions: [{ field: "month", label: "Month", index: 0, role: "time" }],
      measures: [{ field: "n", label: "FIRs", index: 1, unit: "" }],
    });
    wrap(
      <AnswerVisualization
        message={msg({
          visualization: viz,
          columns: ["month", "n"],
          rowsPreview: [
            ["2024-01", 3],
            ["2024-02", 7],
          ],
          rowCount: 2,
        })}
      />,
    );
    expect(screen.getByText(/show data table/i)).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("2024-02")).toBeInTheDocument();
  });

  it("table: renders the rows as the primary, visible table", () => {
    const viz = baseViz({
      kind: "table",
      title: "Matching FIRs",
      dimensions: [{ field: "district", label: "District", index: 0, role: "dimension" }],
      measures: [{ field: "n", label: "FIRs", index: 1, unit: "" }],
    });
    wrap(
      <AnswerVisualization
        message={msg({
          visualization: viz,
          columns: ["district", "n"],
          rowsPreview: [["Bengaluru", 10]],
          rowCount: 1,
        })}
      />,
    );
    const table = screen.getByRole("table"); // defaultOpen => present in the DOM
    expect(within(table).getByText("Bengaluru")).toBeInTheDocument();
  });

  it("choropleth: falls back to the accessible table when boundaries are unavailable", async () => {
    boundaries.mockResolvedValue({ type: "FeatureCollection", features: [] });
    const viz = baseViz({
      kind: "choropleth",
      title: "FIRs by district",
      geo_field: "district",
      dimensions: [{ field: "district", label: "District", index: 0, role: "geo" }],
      measures: [{ field: "n", label: "FIRs", index: 1, unit: "" }],
    });
    wrap(
      <AnswerVisualization
        message={msg({
          visualization: viz,
          columns: ["district", "n"],
          rowsPreview: [["Bagalkot", 12]],
          rowCount: 1,
        })}
      />,
    );
    // once the (empty) boundaries query settles, the map is replaced by the table
    expect(await screen.findByText(/map unavailable/i)).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("Bagalkot")).toBeInTheDocument();
    // the WebGL map is NOT rendered on the fallback path
    expect(screen.queryByTestId("map")).toBeNull();
  });

  it("heatmap: uses the heat ramp and falls back to the accessible table when boundaries unavailable", async () => {
    boundaries.mockResolvedValue({ type: "FeatureCollection", features: [] });
    const viz = baseViz({
      kind: "heatmap",
      title: "Incident density by district",
      geo_field: "district",
      dimensions: [{ field: "district", label: "District", index: 0, role: "geo" }],
      measures: [{ field: "n", label: "FIRs", index: 1, unit: "" }],
    });
    wrap(
      <AnswerVisualization
        message={msg({ visualization: viz, columns: ["district", "n"], rowsPreview: [["Mysuru", 7]], rowCount: 1 })}
      />,
    );
    expect(await screen.findByText(/map unavailable/i)).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("Mysuru")).toBeInTheDocument();
  });

  it("timeline with a time dimension: renders a trend and keeps the accessible table", () => {
    const viz = baseViz({
      kind: "timeline",
      title: "Events over time",
      time_field: "month",
      dimensions: [{ field: "month", label: "Month", index: 0, role: "time" }],
      measures: [{ field: "n", label: "Events", index: 1, unit: "" }],
    });
    wrap(
      <AnswerVisualization
        message={msg({ visualization: viz, columns: ["month", "n"], rowsPreview: [["2024-01", 2], ["2024-02", 5]], rowCount: 2 })}
      />,
    );
    expect(screen.getByText(/show data table/i)).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("2024-02")).toBeInTheDocument();
  });

  it("timeline without a time dimension: renders as an accessible table", () => {
    const viz = baseViz({
      kind: "timeline",
      title: "Case events",
      dimensions: [{ field: "event", label: "Event", index: 0, role: "dimension" }],
      measures: [],
    });
    wrap(
      <AnswerVisualization
        message={msg({ visualization: viz, columns: ["event"], rowsPreview: [["registered"]], rowCount: 1 })}
      />,
    );
    const table = screen.getByRole("table");
    expect(within(table).getByText("registered")).toBeInTheDocument();
  });

  it("network: renders the accessible table with an 'open in Network view' note", () => {
    const viz = baseViz({
      kind: "network",
      title: "Entity network",
      dimensions: [{ field: "a", label: "A", index: 0, role: "dimension" }],
      measures: [],
    });
    wrap(
      <AnswerVisualization
        message={msg({ visualization: viz, columns: ["a", "b"], rowsPreview: [["Person-1", "Person-2"]], rowCount: 1 })}
      />,
    );
    expect(screen.getByText(/open in network view/i)).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("Person-1")).toBeInTheDocument();
  });

  it("sankey: renders the accessible table with an 'open in Sankey view' note", () => {
    const viz = baseViz({
      kind: "sankey",
      title: "Money flow",
      dimensions: [{ field: "src", label: "Source", index: 0, role: "dimension" }],
      measures: [],
    });
    wrap(
      <AnswerVisualization
        message={msg({ visualization: viz, columns: ["src", "dst"], rowsPreview: [["Account-A", "Account-B"]], rowCount: 1 })}
      />,
    );
    expect(screen.getByText(/open in sankey view/i)).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("Account-A")).toBeInTheDocument();
  });

  it("null visualization: still renders the rows_preview table (no regression)", () => {
    wrap(
      <AnswerVisualization
        message={msg({
          visualization: null,
          columns: ["district", "n"],
          rowsPreview: [["Bengaluru", 4]],
          rowCount: 1,
        })}
      />,
    );
    expect(screen.getByText(/results/i)).toBeInTheDocument();
    expect(screen.getByText(/1 row/i)).toBeInTheDocument();
  });

  it("null visualization with no rows: renders nothing", () => {
    const { container } = wrap(
      <AnswerVisualization
        message={msg({ visualization: null, columns: [], rowsPreview: [], rowCount: 0 })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
