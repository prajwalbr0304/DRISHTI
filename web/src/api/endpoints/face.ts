import { apiClient } from "@/api/client";
import type {
  FaceDecisionRequest,
  FaceDecisionResponse,
  FaceDeleteResponse,
  FaceEnrolRequest,
  FaceEnrolResponse,
  FaceListResponse,
  FaceProbeTrailResponse,
  FaceSearchRequest,
  FaceSearchResponse,
  FaceStatusResponse,
} from "@/api/types";

/** Facial recognition (services/ml/app/face). Browser -> FastAPI only.
 *
 *  Probe images travel as base64 in the JSON body because the shared ApiClient is
 *  JSON-only and a probe is a transient query, not evidence — the server keeps its
 *  hash, geometry and descriptor, never the bytes. ALWAYS pass an image through
 *  `prepareFaceImage()` (src/lib/faceCapture.ts) first: it downscales to the long
 *  edge advertised by `status()` so a full-resolution camera frame does not get
 *  rejected by the server's probe size cap. */
export const faceApi = {
  /** GET /face/status — engine, model-weight presence, gallery size, probe counts.
      Drives whether the scan control is enabled and, if not, exactly why. */
  status: (signal?: AbortSignal) =>
    apiClient.get<FaceStatusResponse>("/face/status", undefined, signal),

  /** POST /face/search — 1:N search against the enrolled person gallery.
      Returns a ranked shortlist with each hit's record dossier. `matched` is true
      only when the top hit clears the model threshold; it is still a lead. */
  search: (body: FaceSearchRequest, signal?: AbortSignal) =>
    apiClient.post<FaceSearchResponse>("/face/search", body, undefined, signal),

  /** POST /face/enrol — add a reference photo to a person's gallery. Rejects a
      photo with no detectable face or below the encoder's quality floor. */
  enrol: (body: FaceEnrolRequest, signal?: AbortSignal) =>
    apiClient.post<FaceEnrolResponse>("/face/enrol", body, undefined, signal),

  /** GET /face/persons/{cpid}/faces — enrolled reference photos (metadata only). */
  personFaces: (cpid: number, signal?: AbortSignal) =>
    apiClient.get<FaceListResponse>(`/face/persons/${cpid}/faces`, undefined, signal),

  /** DELETE /face/faces/{id} — retire a reference photo (archived, not deleted). */
  removeFace: (faceId: number, reason?: string, signal?: AbortSignal) =>
    apiClient.request<FaceDeleteResponse>(`/face/faces/${faceId}`, {
      method: "DELETE",
      params: reason ? { reason } : undefined,
      signal,
    }),

  /** POST /face/probes/{ref}/decision — record the officer's disposition.
      Confirming links the shortlisted identity and, when the record already
      carries a different one, raises a face-method review candidate. Never merges. */
  decide: (probeRef: string, body: FaceDecisionRequest, signal?: AbortSignal) =>
    apiClient.post<FaceDecisionResponse>(
      `/face/probes/${encodeURIComponent(probeRef)}/decision`, body, undefined, signal),

  /** GET /face/probes — the biometric-search audit trail. */
  probes: (
    params: { limit?: number; intake_draft_key?: string } = {},
    signal?: AbortSignal,
  ) => apiClient.get<FaceProbeTrailResponse>("/face/probes", params, signal),
};
