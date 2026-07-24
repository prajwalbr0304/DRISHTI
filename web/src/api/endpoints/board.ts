import { apiClient } from "@/api/client";

/* ============================================================================
   Investigation Board (Phase 16). Browser -> Catalyst API Gateway -> AppSail.
   Objects are pinned by REFERENCE (never serialised whole into the URL/state).
   Every mutation returns a MutationResult { version, board_activity_id } used
   for optimistic concurrency + activity replay.
   ========================================================================== */

export type BoardStatus = "active" | "archived" | "locked";
export type BoardVisibility = "private" | "shared" | "unit";
export type EdgeClass = "evidence" | "hypothesis";
export type AnnotationKind = "sticky" | "text" | "frame" | "freehand";
export type CollabRole = "owner" | "editor" | "viewer";

export interface AiResult {
  answer: string;
  confidence: number;
  source_record_ids: string[];
  reasoning_summary: string;
  model_version: string;
}

export interface BoardSummary {
  board_id: number;
  title: string;
  description?: string | null;
  owner_actor: string;
  case_master_id?: number | null;
  status: BoardStatus;
  visibility: BoardVisibility;
  is_locked: boolean;
  version: number;
  parent_board_id?: number | null;
  node_count: number;
  edge_count: number;
  my_role?: CollabRole | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface BoardNodeT {
  board_node_id: number;
  board_id: number;
  node_kind: string;
  ref_table?: string | null;
  ref_id?: string | null;
  canonical_entity_id?: number | null;
  label?: string | null;
  pos_x: number;
  pos_y: number;
  width?: number | null;
  height?: number | null;
  style: Record<string, unknown>;
  snapshot: Record<string, unknown>;
  source_version?: string | null;
  source_hash?: string | null;
  open_in_source?: string | null;
  created_by?: string | null;
  created_at?: string | null;
}

export interface BoardEdgeT {
  board_edge_id: number;
  board_id: number;
  source_node_id: number;
  target_node_id: number;
  edge_class: EdgeClass;
  label?: string | null;
  relationship_type?: string | null;
  directed: boolean;
  confidence?: number | null;
  rationale?: string | null;
  evidence_case_id?: number | null;
  source_record_id?: string | null;
  style: Record<string, unknown>;
  promoted_status?: string | null;
  promoted_ref?: string | null;
  created_by?: string | null;
  created_at?: string | null;
}

export interface BoardAnnotationT {
  board_annotation_id: number;
  board_id: number;
  kind: AnnotationKind;
  content?: string | null;
  geometry: Record<string, unknown>;
  style: Record<string, unknown>;
  created_by?: string | null;
  created_at?: string | null;
}

export interface BoardCollaboratorT {
  board_collaborator_id: number;
  board_id: number;
  actor: string;
  employee_id?: number | null;
  role: CollabRole;
  added_by?: string | null;
  added_at?: string | null;
}

export interface BoardActivityT {
  board_activity_id: number;
  board_id: number;
  actor: string;
  action: string;
  target_type?: string | null;
  target_id?: string | null;
  diff: Record<string, unknown>;
  request_id?: string | null;
  created_at?: string | null;
}

export interface BoardDetail {
  board: BoardSummary;
  nodes: BoardNodeT[];
  edges: BoardEdgeT[];
  annotations: BoardAnnotationT[];
  collaborators: BoardCollaboratorT[];
  latest_activity_id: number;
}

export interface BoardListResponse {
  count: number;
  items: BoardSummary[];
}

export interface MutationResult {
  board_id: number;
  board_activity_id: number;
  version: number;
  target_type?: string | null;
  target_id?: string | null;
  idempotent_replay: boolean;
}

export interface NodeCreate {
  node_kind: string;
  ref_table?: string | null;
  ref_id?: string | null;
  label?: string | null;
  pos_x?: number;
  pos_y?: number;
  width?: number | null;
  height?: number | null;
  style?: Record<string, unknown>;
  snapshot?: Record<string, unknown>;
}

export interface NodePatch {
  pos_x?: number;
  pos_y?: number;
  width?: number | null;
  height?: number | null;
  label?: string | null;
  style?: Record<string, unknown>;
  refresh_snapshot?: boolean;
  expected_version?: number;
  is_move_only?: boolean;
}

export interface EdgeCreate {
  source_node_id: number;
  target_node_id: number;
  edge_class?: EdgeClass;
  label?: string | null;
  relationship_type?: string | null;
  directed?: boolean;
  confidence?: number | null;
  rationale?: string | null;
  style?: Record<string, unknown>;
}

export interface EdgePatch {
  label?: string | null;
  relationship_type?: string | null;
  directed?: boolean;
  confidence?: number | null;
  rationale?: string | null;
  style?: Record<string, unknown>;
  expected_version?: number;
}

export interface AnnotationCreate {
  kind: AnnotationKind;
  content?: string | null;
  geometry?: Record<string, unknown>;
  style?: Record<string, unknown>;
}

export interface SearchAroundNeighbor {
  entity_id: number;
  label?: string | null;
  entity_type?: string | null;
  distance?: number | null;
  relationship_type?: string | null;
  weight: number;
  verified: boolean;
  already_on_board: boolean;
}

export interface SearchAroundResult {
  result: AiResult;
  focal_entity?: number | null;
  hops: number;
  max_neighbors: number;
  node_count: number;
  edge_count: number;
  neighbors: SearchAroundNeighbor[];
  latency_ms: number;
  cached: boolean;
  imported?: MutationResult | null;
}

export interface ReferenceOut {
  ref_table?: string | null;
  ref_id?: string | null;
  node_kind: string;
  exists?: boolean | null;
  label: string;
  canonical_entity_id?: number | null;
  snapshot: Record<string, unknown>;
  source_version?: string | null;
  source_hash?: string | null;
  open_in_source?: string | null;
  detail?: string | null;
  referencing_board_ids: number[];
}

export interface NodeDiff {
  board_node_id: number;
  status: "live" | "changed" | "broken" | "unavailable";
  changed_fields: string[];
  pinned_snapshot: Record<string, unknown>;
  live_snapshot: Record<string, unknown>;
  detail?: string | null;
}

export interface ActivityResponse {
  board_id: number;
  after_id: number;
  latest_activity_id: number;
  count: number;
  items: BoardActivityT[];
}

export interface TableRowT {
  kind: string;
  id: number;
  label?: string | null;
  detail: Record<string, unknown>;
}

export interface TableResponse {
  board_id: number;
  nodes: TableRowT[];
  edges: TableRowT[];
  node_count: number;
  edge_count: number;
  evidence_edge_count: number;
  hypothesis_edge_count: number;
}

export interface TimelineEventT {
  board_activity_id: number;
  at?: string | null;
  actor: string;
  action: string;
  target_type?: string | null;
  target_id?: string | null;
  summary: string;
}

export interface TimelineResponse {
  board_id: number;
  count: number;
  events: TimelineEventT[];
}

export interface ExportOut {
  export_id: string;
  board_id: number;
  format: string;
  object_key: string;
  download_url: string;
  expires_in_s: number;
  sha256: string;
  watermark: string;
  size_bytes?: number | null;
  created_at?: string | null;
}

export interface PresenceActor {
  actor: string;
  selection?: Record<string, unknown> | null;
  cursor?: Record<string, unknown> | null;
  age_s: number;
}

export interface PresenceRoster {
  board_id: number;
  count: number;
  actors: PresenceActor[];
}

export interface CreateBoardBody {
  title: string;
  description?: string | null;
  case_master_id?: number | null;
  visibility?: BoardVisibility;
  unit_id?: number | null;
  district_id?: number | null;
  seed_entity_id?: number | null;
  seed_hops?: number;
  seed_max_neighbors?: number;
}

export interface SearchAroundBody {
  node_id?: number | null;
  entity_id?: number | null;
  hops?: number;
  max_neighbors?: number;
  types?: string[] | null;
  time_from?: string | null;
  time_to?: string | null;
  preview?: boolean;
}

export interface SeedBody {
  ref_table: string;
  ref_id: string;
  node_kind?: string | null;
  label?: string | null;
  expand?: boolean;
  hops?: number;
  max_neighbors?: number;
}

export interface SeedResult {
  board_id: number;
  primary_node_id?: number | null;
  focal_entity?: number | null;
  nodes_added: number;
  edges_added: number;
  expanded: boolean;
  detail: string;
}

export interface BoardPathResult {
  result: AiResult;
  found: boolean;
  method?: string | null;
  hops?: number | null;
  entity_path: number[];
  node_ids: number[];
  nodes_added: number;
  edges_added: number;
  imported?: MutationResult | null;
}

/** Optional idempotency key + If-Match version for a mutation. */
function mutOpts(idemKey?: string, ifMatch?: number): { headers: Record<string, string> } {
  const headers: Record<string, string> = {};
  if (idemKey) headers["X-Idempotency-Key"] = idemKey;
  if (ifMatch != null) headers["If-Match"] = String(ifMatch);
  return { headers };
}

export const boardApi = {
  objectKinds: (signal?: AbortSignal) =>
    apiClient.get<{ node_kinds: string[]; ref_tables: string[] }>(
      "/boards/meta/object-kinds", undefined, signal),

  list: (signal?: AbortSignal) =>
    apiClient.get<BoardListResponse>("/boards", undefined, signal),
  create: (body: CreateBoardBody, signal?: AbortSignal) =>
    apiClient.post<BoardDetail>("/boards", body, undefined, signal),
  get: (boardId: number, signal?: AbortSignal) =>
    apiClient.get<BoardDetail>(`/boards/${boardId}`, undefined, signal),
  patch: (boardId: number, body: Record<string, unknown>, signal?: AbortSignal) =>
    apiClient.request<MutationResult>(`/boards/${boardId}`, { method: "PATCH", body, signal }),
  archive: (boardId: number, signal?: AbortSignal) =>
    apiClient.post<MutationResult>(`/boards/${boardId}/archive`, undefined, undefined, signal),
  lock: (boardId: number, signal?: AbortSignal) =>
    apiClient.post<MutationResult>(`/boards/${boardId}/lock`, undefined, { confirm: true }, signal),
  branch: (boardId: number, title?: string, signal?: AbortSignal) =>
    apiClient.post<BoardDetail>(`/boards/${boardId}/branch`, undefined,
      title ? { title } : undefined, signal),

  // nodes
  addNode: (boardId: number, body: NodeCreate, idemKey?: string, signal?: AbortSignal) =>
    apiClient.request<MutationResult>(`/boards/${boardId}/nodes`,
      { method: "POST", body, signal, ...mutOpts(idemKey) }),
  patchNode: (boardId: number, nodeId: number, body: NodePatch, signal?: AbortSignal) =>
    apiClient.request<MutationResult>(`/boards/${boardId}/nodes/${nodeId}`,
      { method: "PATCH", body, signal, ...mutOpts(undefined, body.expected_version) }),
  deleteNode: (boardId: number, nodeId: number, signal?: AbortSignal) =>
    apiClient.request<MutationResult>(`/boards/${boardId}/nodes/${nodeId}`,
      { method: "DELETE", signal }),

  // edges
  addEdge: (boardId: number, body: EdgeCreate, idemKey?: string, signal?: AbortSignal) =>
    apiClient.request<MutationResult>(`/boards/${boardId}/edges`,
      { method: "POST", body, signal, ...mutOpts(idemKey) }),
  patchEdge: (boardId: number, edgeId: number, body: EdgePatch, signal?: AbortSignal) =>
    apiClient.request<MutationResult>(`/boards/${boardId}/edges/${edgeId}`,
      { method: "PATCH", body, signal, ...mutOpts(undefined, body.expected_version) }),
  deleteEdge: (boardId: number, edgeId: number, signal?: AbortSignal) =>
    apiClient.request<MutationResult>(`/boards/${boardId}/edges/${edgeId}`,
      { method: "DELETE", signal }),

  // annotations
  addAnnotation: (boardId: number, body: AnnotationCreate, signal?: AbortSignal) =>
    apiClient.post<MutationResult>(`/boards/${boardId}/annotations`, body, undefined, signal),
  patchAnnotation: (boardId: number, annotationId: number, body: Record<string, unknown>, signal?: AbortSignal) =>
    apiClient.request<MutationResult>(`/boards/${boardId}/annotations/${annotationId}`,
      { method: "PATCH", body, signal }),
  deleteAnnotation: (boardId: number, annotationId: number, signal?: AbortSignal) =>
    apiClient.request<MutationResult>(`/boards/${boardId}/annotations/${annotationId}`,
      { method: "DELETE", signal }),

  // collaborators
  listCollaborators: (boardId: number, signal?: AbortSignal) =>
    apiClient.get<BoardCollaboratorT[]>(`/boards/${boardId}/collaborators`, undefined, signal),
  addCollaborator: (boardId: number, body: Record<string, unknown>, signal?: AbortSignal) =>
    apiClient.post<MutationResult>(`/boards/${boardId}/collaborators`, body, undefined, signal),
  removeCollaborator: (boardId: number, collaboratorId: number, signal?: AbortSignal) =>
    apiClient.request<MutationResult>(`/boards/${boardId}/collaborators/${collaboratorId}`,
      { method: "DELETE", signal }),

  // search around / import
  searchAround: (boardId: number, body: SearchAroundBody, signal?: AbortSignal) =>
    apiClient.post<SearchAroundResult>(`/boards/${boardId}/search-around`, body, undefined, signal),
  importSubgraph: (boardId: number, body: SearchAroundBody, signal?: AbortSignal) =>
    apiClient.post<SearchAroundResult>(`/boards/${boardId}/import/subgraph`, body, undefined, signal),

  // seed a subgraph on send (case parties / entity neighbourhood); graceful single-pin fallback
  seed: (boardId: number, body: SeedBody, idemKey?: string, signal?: AbortSignal) =>
    apiClient.request<SeedResult>(`/boards/${boardId}/seed`,
      { method: "POST", body, signal, ...mutOpts(idemKey) }),

  // shortest associative path between two entity-backed board nodes (imported as evidence)
  findPath: (boardId: number, sourceNodeId: number, targetNodeId: number, signal?: AbortSignal) =>
    apiClient.post<BoardPathResult>(`/boards/${boardId}/path`,
      { source_node_id: sourceNodeId, target_node_id: targetNodeId }, undefined, signal),

  // promotion
  promoteEdge: (boardId: number, edgeId: number, note?: string, signal?: AbortSignal) =>
    apiClient.post<MutationResult>(`/boards/${boardId}/promote-edge/${edgeId}`,
      { confirm: true, note }, undefined, signal),

  // helpers
  activity: (boardId: number, afterId = 0, signal?: AbortSignal) =>
    apiClient.get<ActivityResponse>(`/boards/${boardId}/activity`, { after_id: afterId }, signal),
  table: (boardId: number, signal?: AbortSignal) =>
    apiClient.get<TableResponse>(`/boards/${boardId}/table`, undefined, signal),
  timeline: (boardId: number, params: { window_start?: string; window_end?: string } = {}, signal?: AbortSignal) =>
    apiClient.get<TimelineResponse>(`/boards/${boardId}/timeline`, params, signal),
  diffs: (boardId: number, signal?: AbortSignal) =>
    apiClient.get<NodeDiff[]>(`/boards/${boardId}/diffs`, undefined, signal),
  reference: (refTable: string, refId: string, signal?: AbortSignal) =>
    apiClient.get<ReferenceOut>(`/boards/references/${encodeURIComponent(refTable)}/${encodeURIComponent(refId)}`,
      undefined, signal),
  benchmark: (boardId: number, entityId: number, signal?: AbortSignal) =>
    apiClient.get<Record<string, unknown>>(`/boards/${boardId}/benchmark/search-around`,
      { entity_id: entityId }, signal),

  // presence (ephemeral, throttled, NoSQL/TTL)
  presenceBeat: (boardId: number, body: { selection?: Record<string, unknown>; cursor?: Record<string, unknown> }, signal?: AbortSignal) =>
    apiClient.post<PresenceRoster>(`/boards/${boardId}/presence`, body, undefined, signal),
  presenceRoster: (boardId: number, signal?: AbortSignal) =>
    apiClient.get<PresenceRoster>(`/boards/${boardId}/presence`, undefined, signal),

  // export / import
  export: (boardId: number, format: "json" | "pdf" = "json", signal?: AbortSignal) =>
    apiClient.post<ExportOut>(`/boards/${boardId}/export`, { format, confirm: true }, undefined, signal),
  getExport: (boardId: number, exportId: string, signal?: AbortSignal) =>
    apiClient.get<ExportOut>(`/boards/${boardId}/export/${exportId}`, undefined, signal),
  importBoard: (document: Record<string, unknown>, signal?: AbortSignal) =>
    apiClient.post<BoardDetail>("/boards/import", document, undefined, signal),
};
