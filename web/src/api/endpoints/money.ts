import { apiClient } from "@/api/client";
import type {
  DetectionResponse,
  FlaggedFeedResponse,
  TraceResponse,
  UnifiedResponse,
} from "@/api/types";

export type DetectParams = {
  structuring_min_count?: number;
  structuring_window_days?: number;
  cycle_min_amount?: number;
  cycle_max_len?: number;
};

/**
 * Phase-11 money-trail engine (services/ml/app/money). All routes are gated by
 * the caller's role (sent as X-Role); the shell hides this destination for
 * roles without the money_trail permission.
 */
export const moneyApi = {
  trace: (account: number, max_hops = 4, signal?: AbortSignal) =>
    apiClient.get<TraceResponse>("/money/trace", { account, max_hops }, signal),

  unified: (
    seed: { entity_id: number } | { account_id: number },
    max_hops = 2,
    signal?: AbortSignal,
  ) => apiClient.get<UnifiedResponse>("/money/unified", { ...seed, max_hops }, signal),

  flagged: (
    opts: { page?: number; page_size?: number; reason?: string } = {},
    signal?: AbortSignal,
  ) => apiClient.get<FlaggedFeedResponse>("/money/flagged", { page: 1, page_size: 25, ...opts }, signal),

  detect: (params: DetectParams = {}, signal?: AbortSignal) =>
    apiClient.post<DetectionResponse>("/money/detect", undefined, params, signal),
};
