import { apiClient } from "@/api/client";
import { analyticsApi } from "@/api/endpoints/analytics";
import { casesApi } from "@/api/endpoints/cases";
import { chatApi } from "@/api/endpoints/chat";
import { explainApi } from "@/api/endpoints/explain";
import { forecastApi } from "@/api/endpoints/forecast";
import { geoApi } from "@/api/endpoints/geo";
import { graphApi } from "@/api/endpoints/graph";
import { moneyApi } from "@/api/endpoints/money";
import { riskApi } from "@/api/endpoints/risk";

/**
 * The single typed entry point to every Wave-B service. Import `api` anywhere
 * (usually inside a react-query `queryFn`). All calls are live; failures throw
 * ApiError so components render honest loading / empty / error states.
 */
export const api = {
  health: (signal?: AbortSignal) => apiClient.health(signal),
  cases: casesApi,
  geo: geoApi,
  graph: graphApi,
  analytics: analyticsApi,
  risk: riskApi,
  money: moneyApi,
  forecast: forecastApi,
  explain: explainApi,
  chat: chatApi,
};

export { apiClient };
export * from "@/api/contracts";
export * from "@/api/types";
