/* ============================================================================
   Cross-service contracts shared by every DRISHTI AI/analytics response.
   These mirror services/ml/app/contracts.py exactly.

   Every intelligence endpoint returns a typed *envelope* that embeds an
   AiResult under `result`, alongside its typed payload. The universal <Widget>
   provenance strip binds directly to that `result` (the Evidence contract).
   ========================================================================== */

/**
 * The single provenance/answer shape every AI/analytics endpoint returns
 * (embedded as `result` inside each typed envelope). Backend: contracts.AiResult.
 */
export interface AiResult {
  /** Human-readable result / decision-support statement. */
  answer: string;
  /** Calibrated confidence in [0, 1]. */
  confidence: number;
  /** Provenance: DB record ids backing this answer, e.g. "CaseMaster:123". */
  source_record_ids: string[];
  /** Short plain-language rationale (never chain-of-thought). */
  reasoning_summary: string;
  /** ModelName@Version of the model that produced this. */
  model_version: string;
}

/** Any typed endpoint envelope carries an AiResult under `result`. */
export interface Envelope {
  result: AiResult;
}

/** Health probe returned by GET /health. Backend: contracts.HealthReport. */
export interface HealthReport {
  status: "ok" | "degraded";
  app: string;
  version: string;
  database: boolean;
  extensions: Record<string, boolean>;
  detail: string;
}

/** Normalised API error surfaced to the UI. */
export class ApiError extends Error {
  status: number;
  detail?: unknown;
  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Best-effort human message from an unknown thrown value. */
export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.detail && typeof e.detail === "object" && "detail" in e.detail) {
      const d = (e.detail as { detail?: unknown }).detail;
      if (typeof d === "string") return d;
    }
    return e.message;
  }
  if (e instanceof Error) return e.message;
  return String(e);
}
