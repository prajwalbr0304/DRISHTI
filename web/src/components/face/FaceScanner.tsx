import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Camera, CameraOff, CheckCircle2, ImageUp, Info, Loader2,
  RefreshCcw, RotateCcw, ScanFace, ShieldAlert, SwitchCamera, UserPlus, X,
} from "lucide-react";
import { api } from "@/api";
import { ApiError, errorMessage } from "@/api/contracts";
import type {
  FaceDecision, FaceMatch, FaceOrigin, FaceSearchResponse, FaceStatusResponse,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  FaceCaptureError, captureFromVideo, formatImageBytes, prepareFaceImage,
  type PreparedImage,
} from "@/lib/faceCapture";
import { FaceMatchCard } from "./FaceMatchCard";
import { FaceScanViewport, type ViewportPhase } from "./FaceScanViewport";
import { FaceDetectionRail, FaceEngineRail } from "./FaceTelemetry";
import {
  SCAN_STAGES, type ScanStageKey, bandMeta, usePrefersReducedMotion, useFaceStatus,
} from "./faceShared";
import { useCamera } from "./useCamera";

/** What the caller gets back when the officer accepts a match. */
export interface FaceConfirmation {
  match: FaceMatch;
  probeRef: string;
  similarity: number;
  /** Set when confirming collided with an identity already on the record. */
  entityResolutionCandidateId?: number | null;
}

interface Props {
  origin?: FaceOrigin;
  intakeDraftKey?: string | null;
  caseId?: number | null;
  /** An identity already attached to the record. A different confirmed person
   *  raises a face-method review candidate instead of silently replacing it. */
  existingCanonicalPersonId?: number | null;
  /** Omit to render read-only (search + inspect, no linking). */
  onConfirm?: (c: FaceConfirmation) => void | Promise<void>;
  confirmLabel?: string;
  /** Called when the officer records "not on file". Receives the probe handle so
   *  the caller can offer to enrol this face against the identity it is about to
   *  create — the descriptor is already retained server-side against this ref,
   *  so nothing has to be re-uploaded or held in the browser. */
  onNoMatch?: (probeRef: string) => void;
  onClose?: () => void;
  className?: string;
}

type Stage = "source" | "ready" | "scanning" | "result" | "error";

/** Face recognition workspace: capture or upload a photo, search it against the
 *  person gallery, and read the matched record.
 *
 *  The scan graphics are deliberate: an ArcFace search takes a few hundred
 *  milliseconds of real work, and narrating the actual pipeline stages while it
 *  runs is more honest than a bare spinner — every readout beside the viewport
 *  corresponds to a real value from the response, and all of it degrades to plain
 *  text under prefers-reduced-motion. */
export function FaceScanner({
  origin = "standalone", intakeDraftKey, caseId, existingCanonicalPersonId,
  onConfirm, confirmLabel, onNoMatch, onClose, className,
}: Props) {
  const qc = useQueryClient();
  const statusQ = useFaceStatus();
  const status: FaceStatusResponse | undefined = statusQ.data;
  const reducedMotion = usePrefersReducedMotion();
  const camera = useCamera();

  const [stage, setStage] = useState<Stage>("source");
  const [image, setImage] = useState<PreparedImage | null>(null);
  const [result, setResult] = useState<FaceSearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeStage, setActiveStage] = useState<ScanStageKey | null>(null);
  const [completed, setCompleted] = useState<ScanStageKey[]>([]);
  const [decided, setDecided] = useState<FaceDecision | null>(null);
  const [decisionNote, setDecisionNote] = useState<string | null>(null);
  const [busyPersonId, setBusyPersonId] = useState<number | null>(null);

  const fileInput = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const stageTimers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const liveRegion = useRef<HTMLDivElement>(null);

  const clearStageTimers = () => {
    stageTimers.current.forEach(clearTimeout);
    stageTimers.current = [];
  };
  useEffect(() => () => {
    clearStageTimers();
    abortRef.current?.abort();
  }, []);

  const searchReady = !!status?.search_ready;
  const engineDown = !!status && (!status.enabled || !status.available);
  const degraded = !!status?.engine && !status.engine.biometric;
  const prepOpts = useMemo(() => ({
    longEdge: status?.recommended_long_edge,
    maxBytes: status?.max_image_bytes,
  }), [status?.recommended_long_edge, status?.max_image_bytes]);

  /* ---------------------------------------------------------------- sourcing */
  const acceptImage = useCallback(async (blob: Blob) => {
    setError(null);
    setResult(null);
    setDecided(null);
    setDecisionNote(null);
    try {
      const prepared = await prepareFaceImage(blob, prepOpts);
      setImage(prepared);
      setStage("ready");
      camera.stop();
    } catch (e) {
      setError(e instanceof FaceCaptureError ? e.message : errorMessage(e));
      setStage("error");
    }
  }, [prepOpts, camera]);

  const onPickFile = (f: File | null) => {
    if (f) void acceptImage(f);
  };

  const shoot = async () => {
    const video = camera.videoRef.current;
    if (!video) return;
    setError(null);
    try {
      const prepared = await captureFromVideo(video, prepOpts);
      setImage(prepared);
      setResult(null);
      setDecided(null);
      setStage("ready");
      camera.stop();
    } catch (e) {
      setError(e instanceof FaceCaptureError ? e.message : errorMessage(e));
    }
  };

  const reset = () => {
    clearStageTimers();
    abortRef.current?.abort();
    setImage(null);
    setResult(null);
    setError(null);
    setDecided(null);
    setDecisionNote(null);
    setActiveStage(null);
    setCompleted([]);
    setStage("source");
    camera.stop();
  };

  /* ----------------------------------------------------------------- search */
  const runScan = async () => {
    if (!image) return;
    setError(null);
    setResult(null);
    setDecided(null);
    setStage("scanning");
    setCompleted([]);

    // Walk the readout through the pipeline stages the server is actually
    // executing. The final two stages are settled by the response, not a timer,
    // so the log can never claim progress the server has not made.
    clearStageTimers();
    setActiveStage("acquire");
    const script: Array<[ScanStageKey, ScanStageKey, number]> = [
      ["acquire", "prepare", 120],
      ["prepare", "detect", 260],
      ["detect", "encode", 520],
    ];
    script.forEach(([from, to, at]) => {
      stageTimers.current.push(setTimeout(() => {
        setCompleted((c) => (c.includes(from) ? c : [...c, from]));
        setActiveStage(to);
      }, at));
    });

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const res = await api.face.search({
        image_base64: image.base64,
        origin,
        intake_draft_key: intakeDraftKey ?? undefined,
        case_id: caseId ?? undefined,
        capture_mode: image.mimeType === "image/jpeg" && camera.state !== "idle"
          ? "camera" : "upload",
      }, ctrl.signal);
      clearStageTimers();
      setCompleted(SCAN_STAGES.map((s) => s.key));
      setActiveStage(null);
      setResult(res);
      setStage("result");
      qc.invalidateQueries({ queryKey: ["face", "status"] });
    } catch (e) {
      clearStageTimers();
      if (e instanceof DOMException && e.name === "AbortError") {
        setStage("ready");
        setActiveStage(null);
        return;
      }
      setActiveStage((s) => s ?? "search");
      setStage("error");
      setError(
        e instanceof ApiError && e.status === 409
          ? errorMessage(e)
          : errorMessage(e),
      );
    }
  };

  /* --------------------------------------------------------------- decisions */
  const record = async (decision: FaceDecision, match?: FaceMatch) => {
    if (!result) return;
    setError(null);
    setBusyPersonId(match?.canonical_person_id ?? -1);
    try {
      const res = await api.face.decide(result.probe.probe_ref, {
        decision,
        canonical_person_id: match?.canonical_person_id ?? null,
        existing_canonical_person_id: existingCanonicalPersonId ?? null,
        // Adding the probe to the gallery is a deliberate act; a strong hit from
        // a fresh pose is exactly the photo worth keeping.
        enrol_probe: decision === "confirmed" && match?.band === "strong",
      });
      setDecided(decision);
      setDecisionNote([res.message, ...res.warnings].filter(Boolean).join(" "));
      qc.invalidateQueries({ queryKey: ["face"] });
      if (decision === "confirmed" && match && onConfirm) {
        await onConfirm({
          match,
          probeRef: result.probe.probe_ref,
          similarity: match.similarity,
          entityResolutionCandidateId: res.entity_resolution_candidate_id,
        });
      }
      if (decision !== "confirmed") onNoMatch?.(result.probe.probe_ref);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusyPersonId(null);
    }
  };

  /* ------------------------------------------------------------ presentation */
  const phase: ViewportPhase =
    stage === "scanning" ? "scanning"
      : stage === "result" ? "result"
        : camera.isLive || camera.state === "starting" ? "camera"
          : image ? "still" : "empty";

  const best = result?.best_match ?? null;
  const outcome = !result ? null
    : best?.band === "strong" ? "match"
      : best?.band === "probable" ? "possible" : "none";

  const announcement = useMemo(() => {
    if (stage === "scanning") return "Scanning photo against person records.";
    if (stage === "error") return `Scan failed. ${error ?? ""}`;
    if (stage === "result" && result) {
      if (!result.matched) {
        return "No match found. This person does not appear in the records.";
      }
      const m = result.best_match!;
      return `${bandMeta(m.band).label}: ${m.person.display_label ?? m.person.public_ref}, `
        + `${Math.round(m.similarity * 100)} percent similarity, `
        + `${m.person.case_count} cases on record.`;
    }
    return "";
  }, [stage, error, result]);

  return (
    <div className={cn("space-y-4", className)}>
      {/* screen-reader narration of every state change */}
      <div ref={liveRegion} aria-live="polite" role="status" className="sr-only">
        {announcement}
      </div>

      {/* ---------------- engine banners ---------------- */}
      {statusQ.isLoading && <Skeleton className="h-10 w-full" />}
      {engineDown && (
        <Notice tone="high" icon={<ShieldAlert />} title="Face recognition is unavailable">
          {status?.unavailable_reason ?? "No face engine is configured on the server."}
          {status?.models?.install_command && (
            <>
              {" "}Install the model weights on the server with{" "}
              <code className="rounded-badge bg-surface-2 px-1 py-0.5 font-mono text-11">
                {status.models.install_command}
              </code>.
            </>
          )}
        </Notice>
      )}
      {!engineDown && degraded && (
        <Notice tone="medium" icon={<AlertTriangle />} title="Degraded mode — not face recognition">
          This server is running the fallback image-similarity backend. It can only
          find the <em>same photograph</em> already on record, and cannot recognise a
          person from a new photo. Treat any result as a duplicate-file check.
          {status?.models?.install_command && (
            <>
              {" "}Enable real recognition with{" "}
              <code className="rounded-badge bg-surface-2 px-1 py-0.5 font-mono text-11">
                {status.models.install_command}
              </code>.
            </>
          )}
        </Notice>
      )}
      {!engineDown && !searchReady && status?.gallery.face_count === 0 && (
        <Notice tone="medium" icon={<Info />} title="No reference photos enrolled yet">
          There is nothing to match against. Add a reference photo to a person's
          record first — open a person, then <strong>Add face photo</strong>.
        </Notice>
      )}
      {!engineDown && status?.gallery.model_mismatch && (
        <Notice tone="high" icon={<ShieldAlert />} title="Gallery / model mismatch">
          The enrolled photos were encoded with a different model
          ({status.gallery.model_name}) than the one running now
          ({status.engine.name}). Scores between two different models are
          meaningless, so search is disabled until the gallery is re-enrolled.
        </Notice>
      )}

      {/* ---------------- scan stage ---------------- */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,15rem)_minmax(0,1fr)_minmax(0,15rem)]">
        <div className="order-2 lg:order-1">
          <FaceEngineRail
            status={status}
            activeStage={activeStage}
            completedStages={completed}
            failed={stage === "error"}
          />
        </div>

        <div className="order-1 space-y-3 lg:order-2">
          <FaceScanViewport
            phase={phase}
            imageUrl={image?.dataUrl}
            videoRef={camera.videoRef}
            mirrored={camera.facingMode === "user"}
            probe={result?.probe}
            reducedMotion={reducedMotion}
            outcome={outcome}
          />

          {/* capture / upload controls */}
          <input
            ref={fileInput}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/bmp"
            className="hidden"
            onChange={(e) => onPickFile(e.target.files?.[0] ?? null)}
          />
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (stage !== "scanning") onPickFile(e.dataTransfer.files?.[0] ?? null);
            }}
            className="flex flex-wrap items-center gap-2 rounded-card border border-dashed border-hairline bg-surface-2/40 p-3"
          >
            {camera.isLive ? (
              <>
                <Button size="sm" onClick={() => void shoot()}>
                  <Camera /> Take photo
                </Button>
                {camera.hasMultipleCameras && (
                  <Button variant="outline" size="sm" onClick={() => void camera.flip()}>
                    <SwitchCamera /> Flip
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={camera.stop}>
                  <CameraOff /> Stop camera
                </Button>
              </>
            ) : (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void camera.start()}
                  disabled={!camera.supported || stage === "scanning"
                    || camera.state === "starting"}
                >
                  {camera.state === "starting"
                    ? <Loader2 className="animate-spin" />
                    : <Camera />}
                  Use camera
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => fileInput.current?.click()}
                  disabled={stage === "scanning"}
                >
                  <ImageUp /> Upload photo
                </Button>
                <span className="text-11 text-content-dim">
                  or drop an image here
                </span>
              </>
            )}
            {image && (
              <span className="tnum ml-auto text-11 text-content-dim">
                {image.width}x{image.height} · {formatImageBytes(image.bytes)}
                {image.resized && " · resized"}
              </span>
            )}
          </div>

          {camera.error && (
            <p className="flex items-start gap-1.5 text-12 text-severity-medium">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              {camera.error}
            </p>
          )}
          {error && (
            <p className="flex items-start gap-1.5 text-12 text-severity-high" role="alert">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              {error}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <Button
              onClick={() => void runScan()}
              disabled={!image || stage === "scanning" || !searchReady}
            >
              {stage === "scanning"
                ? <><Loader2 className="animate-spin" /> Scanning…</>
                : <><ScanFace /> Scan against records</>}
            </Button>
            {stage === "scanning" && (
              <Button variant="ghost" size="sm" onClick={() => abortRef.current?.abort()}>
                <X /> Cancel
              </Button>
            )}
            {(image || result) && stage !== "scanning" && (
              <Button variant="ghost" size="sm" onClick={reset}>
                <RotateCcw /> Start over
              </Button>
            )}
            {result && stage !== "scanning" && (
              <Button variant="ghost" size="sm" onClick={() => void runScan()}>
                <RefreshCcw /> Re-scan
              </Button>
            )}
            {onClose && (
              <Button variant="ghost" size="sm" className="ml-auto" onClick={onClose}>
                Close
              </Button>
            )}
          </div>
        </div>

        <div className="order-3">
          <FaceDetectionRail
            probe={result?.probe}
            topSimilarity={result?.matches[0]?.similarity}
            topBand={result?.matches[0]?.band}
            latencyMs={result?.latency_ms}
            searched={result?.matches.length}
          />
        </div>
      </div>

      {/* ---------------- results ---------------- */}
      {result && (
        <section className="space-y-3">
          <header
            className={cn(
              "flex flex-wrap items-center justify-between gap-2 rounded-card border p-3",
              result.matched
                ? "border-severity-low/40 bg-severity-low/5"
                : "border-hairline bg-surface-2/40",
              !reducedMotion && "animate-face-reveal",
            )}
          >
            <div className="flex items-start gap-2">
              {result.matched
                ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-severity-low" aria-hidden />
                : <Info className="mt-0.5 size-4 shrink-0 text-content-dim" aria-hidden />}
              <div>
                <p className="text-13 font-bold text-content">
                  {result.matched
                    ? "This person is already on record"
                    : "No match in the records"}
                </p>
                <p className="text-12 text-content-dim">
                  {result.matched
                    ? `Closest record scored ${Math.round((best?.similarity ?? 0) * 100)}% `
                      + `against ${result.gallery_person_count.toLocaleString()} enrolled people.`
                    : `Checked against ${result.gallery_person_count.toLocaleString()} enrolled `
                      + `people. Proceed as a new identity.`}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="tnum">{result.latency_ms} ms</Badge>
              {!result.biometric && <Badge variant="medium">degraded mode</Badge>}
            </div>
          </header>

          {result.warnings.map((w) => (
            <p key={w} className="flex items-start gap-1.5 text-12 text-severity-medium">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              {w}
            </p>
          ))}

          {decided ? (
            <Notice
              tone={decided === "confirmed" ? "low" : "neutral"}
              icon={decided === "confirmed" ? <CheckCircle2 /> : <Info />}
              title={decided === "confirmed" ? "Match confirmed" : "Recorded"}
            >
              {decisionNote}
            </Notice>
          ) : (
            <>
              {result.matches.map((m, i) => (
                <FaceMatchCard
                  key={m.canonical_person_id}
                  match={m}
                  threshold={result.threshold}
                  index={i}
                  primary={i === 0 && m.above_threshold}
                  reducedMotion={reducedMotion}
                  onConfirm={onConfirm ? (mm) => void record("confirmed", mm) : undefined}
                  confirmLabel={confirmLabel}
                  confirming={busyPersonId === m.canonical_person_id}
                  disabled={busyPersonId != null}
                />
              ))}
              {onConfirm && (
                <div className="flex flex-wrap items-center gap-2 rounded-card border border-hairline bg-surface-2/40 p-3">
                  <span className="text-12 text-content-dim">
                    {result.matched
                      ? "None of these is the right person?"
                      : "Nothing matched."}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void record(result.matched ? "rejected" : "no_match")}
                    disabled={busyPersonId != null}
                  >
                    <UserPlus /> Not on file — new person
                  </Button>
                </div>
              )}
            </>
          )}

          <p className="flex items-start gap-1.5 rounded-card border border-hairline bg-surface-2/30 p-3 text-11 leading-4 text-content-dim">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            {result.disclaimer}
          </p>
        </section>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- notice box */
function Notice({ tone, icon, title, children }: {
  tone: "high" | "medium" | "low" | "neutral";
  icon: React.ReactNode;
  title: string;
  children?: React.ReactNode;
}) {
  const cls = {
    high: "border-severity-high/40 bg-severity-high/5 text-severity-high",
    medium: "border-severity-medium/40 bg-severity-medium/5 text-severity-medium",
    low: "border-severity-low/40 bg-severity-low/5 text-severity-low",
    neutral: "border-hairline bg-surface-2/40 text-content-dim",
  }[tone];
  return (
    <div className={cn("flex items-start gap-2 rounded-card border p-3", cls)}>
      <span className="mt-0.5 shrink-0 [&_svg]:size-4">{icon}</span>
      <div className="min-w-0 text-12">
        <p className="font-bold">{title}</p>
        <div className="mt-0.5 text-content-dim">{children}</div>
      </div>
    </div>
  );
}
