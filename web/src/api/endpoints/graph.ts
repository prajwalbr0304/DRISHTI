import { apiClient } from "@/api/client";
import type {
  CentralityResponse,
  CommunitiesResponse,
  HiddenFeedResponse,
  PathResponse,
  ProofPathResponse,
  SubgraphResponse,
} from "@/api/types";

/** Phase-6 graph-analysis engine + Phase-15d entity explorer. */
export const graphApi = {
  /** GET /graph/entities — paginated, filterable entity index. */
  entities: (
    params: {
      q?: string;
      entity_type?: string;
      has_risk?: boolean;
      gang_affiliated?: boolean;
      district_id?: number;
      page?: number;
      page_size?: number;
    } = {},
    signal?: AbortSignal,
  ) => apiClient.get<import("@/api/types").EntityListResponse>("/graph/entities", params, signal),

  /** GET /graph/entities/{id} — full entity profile. */
  entityDetail: (entityId: number, signal?: AbortSignal) =>
    apiClient.get<import("@/api/types").EntityDetailResponse>(`/graph/entities/${entityId}`, undefined, signal),

  /** GET /graph/communities/list — communities ranked by size + gang cross-ref. */
  communitiesList: (limit = 40, signal?: AbortSignal) =>
    apiClient.get<import("@/api/types").CommunityListResponse>("/graph/communities/list", { limit }, signal),

  /** GET /graph/communities/{id}/subgraph — top members + induced edges. */
  communitySubgraph: (communityId: number, limit = 60, signal?: AbortSignal) =>
    apiClient.get<import("@/api/types").CommunitySubgraphResponse>(
      `/graph/communities/${communityId}/subgraph`,
      { limit },
      signal,
    ),

  neighbourhood: (entity_id: number, max_hops = 2, top_n = 15, signal?: AbortSignal) =>
    apiClient.get<SubgraphResponse>("/graph/neighbourhood", { entity_id, max_hops, top_n }, signal),

  path: (source: number, target: number, signal?: AbortSignal) =>
    apiClient.get<PathResponse>("/graph/path", { source, target }, signal),

  communities: (signal?: AbortSignal) =>
    apiClient.post<CommunitiesResponse>("/graph/communities", undefined, undefined, signal),

  centrality: (top = 20, entity_type = "person", signal?: AbortSignal) =>
    apiClient.get<CentralityResponse>("/graph/centrality", { top, entity_type }, signal),

  hiddenAssociations: (
    opts: { page?: number; page_size?: number; min_links?: number; refresh?: boolean } = {},
    signal?: AbortSignal,
  ) =>
    apiClient.post<HiddenFeedResponse>(
      "/graph/hidden-associations",
      undefined,
      { page: 1, page_size: 20, min_links: 2, refresh: false, ...opts },
      signal,
    ),

  proofPath: (association_id: number, signal?: AbortSignal) =>
    apiClient.get<ProofPathResponse>("/graph/proof-path", { association_id }, signal),
};
