import { apiClient } from "@/api/client";
import { adminApi } from "@/api/endpoints/admin";
import { analyticsApi } from "@/api/endpoints/analytics";
import { boardApi } from "@/api/endpoints/board";
import { casesApi } from "@/api/endpoints/cases";
import { disasterApi } from "@/api/endpoints/disaster";
import { caseworkApi } from "@/api/endpoints/casework";
import { chatApi } from "@/api/endpoints/chat";
import { evidenceApi } from "@/api/endpoints/evidence";
import { explainApi } from "@/api/endpoints/explain";
import { forecastApi } from "@/api/endpoints/forecast";
import { geoApi } from "@/api/endpoints/geo";
import { governanceApi } from "@/api/endpoints/governance";
import { graphApi } from "@/api/endpoints/graph";
import { identityApi } from "@/api/endpoints/identity";
import { importsApi } from "@/api/endpoints/imports";
import { intakeApi } from "@/api/endpoints/intake";
import { investigateApi } from "@/api/endpoints/investigate";
import { livefeedApi } from "@/api/endpoints/livefeed";
import { moneyApi } from "@/api/endpoints/money";
import { notificationsApi } from "@/api/endpoints/notifications";
import { orgApi } from "@/api/endpoints/org";
import { performanceApi } from "@/api/endpoints/performance";
import { ragApi } from "@/api/endpoints/rag";
import { reportsApi } from "@/api/endpoints/reports";
import { riskApi } from "@/api/endpoints/risk";
import { workloadApi } from "@/api/endpoints/workload";

/**
 * The single typed entry point to every Wave-B service. Import `api` anywhere
 * (usually inside a react-query `queryFn`). All calls are live; failures throw
 * ApiError so components render honest loading / empty / error states.
 */
export const api = {
  health: (signal?: AbortSignal) => apiClient.health(signal),
  cases: casesApi,
  casework: caseworkApi,
  evidence: evidenceApi,
  geo: geoApi,
  graph: graphApi,
  identity: identityApi,
  imports: importsApi,
  intake: intakeApi,
  investigate: investigateApi,
  livefeed: livefeedApi,
  analytics: analyticsApi,
  risk: riskApi,
  money: moneyApi,
  forecast: forecastApi,
  explain: explainApi,
  chat: chatApi,
  governance: governanceApi,
  workload: workloadApi,
  admin: adminApi,
  org: orgApi,
  performance: performanceApi,
  notifications: notificationsApi,
  reports: reportsApi,
  rag: ragApi,
  board: boardApi,
  disaster: disasterApi,
};

export { apiClient };
export * from "@/api/contracts";
export * from "@/api/types";
