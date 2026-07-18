import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

const features = vi.fn();
const schemas = vi.fn();
const models = vi.fn();
vi.mock("@/api", () => ({
  api: {
    governance: {
      features: (...a: unknown[]) => features(...a),
      schemas: (...a: unknown[]) => schemas(...a),
      models: (...a: unknown[]) => models(...a),
      snapshots: vi.fn(), labels: vi.fn(), predictions: vi.fn(), prediction: vi.fn(),
      buildSnapshot: vi.fn(), createPrediction: vi.fn(), runPrediction: vi.fn(),
      reviewPrediction: vi.fn(), invalidateSnapshot: vi.fn(), rollbackModel: vi.fn(),
    },
  },
}));

import { GovernanceRegistry } from "@/routes/governance/GovernanceRegistry";
import { RoleProvider } from "@/providers/RoleProvider";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RoleProvider>
        <MemoryRouter>{node}</MemoryRouter>
      </RoleProvider>
    </QueryClientProvider>,
  );
}

describe("GovernanceRegistry", () => {
  beforeEach(() => {
    features.mockReset(); schemas.mockReset(); models.mockReset();
    features.mockResolvedValue({
      total: 1,
      items: [{
        feature_definition_id: 1, name: "area_incident_count_precutoff", value_type: "numeric",
        observation_cutoff_behavior: "strict_pre_cutoff", sensitivity: "normal", allowed_tasks: ["area_incident_forecast"],
        missing_policy: "null_ok", stale_policy: "invalidate_on_source_change", approval_status: "approved",
      }],
    });
    schemas.mockResolvedValue({
      total: 1,
      items: [{
        feature_schema_version_id: 1, schema_name: "area_forecast_features", version: "1",
        feature_definition_ids: [1], task: "area_incident_forecast", status: "approved",
        features: [{ feature_definition_id: 1, name: "area_incident_count_precutoff", value_type: "numeric",
          observation_cutoff_behavior: "strict_pre_cutoff", sensitivity: "normal", allowed_tasks: [],
          missing_policy: "null_ok", stale_policy: "x", approval_status: "approved" }],
        has_protected_feature: false,
      }],
    });
    models.mockResolvedValue({
      total: 1,
      items: [{
        model_version_id: 5, model_name: "area_incident_forecast_baseline", version: "v2-demo",
        approval_status: "approved", feature_schema_version_id: 1, evaluation_report: {},
        is_rollback_target: false, environment: "hackathon_demo", artifact_digest: "sha256:demo",
      }],
    });
  });

  it("renders the feature catalogue, a no-protected schema and a governed model", async () => {
    wrap(<GovernanceRegistry />);
    expect(screen.getByText("Model governance")).toBeInTheDocument();
    expect(screen.getByText("Synthetic Hackathon Demo")).toBeInTheDocument();
    // feature catalogue row
    expect(await screen.findAllByText("area_incident_count_precutoff")).not.toHaveLength(0);
    // schema shows the protected-free guarantee
    expect(await screen.findByText(/no protected/i)).toBeInTheDocument();
    // governed model version
    expect(await screen.findByText("area_incident_forecast_baseline@v2-demo")).toBeInTheDocument();
  });
});
