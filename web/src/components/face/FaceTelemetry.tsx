import type { ReactNode } from "react";
import {
  AlertTriangle, Check, CircleDashed, Cpu, Database, Gauge, Loader2,
  ScanFace, ShieldCheck, Target,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { FaceProbeInfo, FaceStatusResponse } from "@/api/types";
import { SCAN_STAGES, type ScanStageKey, similarityPct } from "./faceShared";

/* The rails flanking the scan viewport. Everything the overlay graphics imply is
   written here in words and numbers, so the readout — not the animation — is the
   source of truth. */

function Readout({ icon, label, value, hint, tone }: {
  icon: ReactNode; label: string; value: ReactNode; hint?: string;
  tone?: "default" | "dim" | "warn";
}) {
  return (
    <div className="space-y-0.5">
      <div className="flex items-center gap-1.5 text-11 uppercase tracking-wide text-content-dim">
        <span className="[&_svg]:size-3">{icon}</span>
        {label}
      </div>
      <div
        className={cn(
          "tnum truncate text-13 font-medium",
          tone === "warn" ? "text-severity-medium"
            : tone === "dim" ? "text-content-dim" : "text-content",
        )}
        title={typeof value === "string" ? value : undefined}
      >
        {value}
      </div>
      {hint && <p className="text-11 leading-4 text-content-dim">{hint}</p>}
    </div>
  );
}

function Rail({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-3 rounded-card border border-hairline bg-surface-2/40 p-3">
      <h4 className="text-11 font-bold uppercase tracking-wider text-content-dim">
        {title}
      </h4>
      {children}
    </div>
  );
}

/** Left rail — the engine and gallery being searched, plus a live stage log. */
export function FaceEngineRail({ status, activeStage, completedStages, failed }: {
  status?: FaceStatusResponse;
  activeStage?: ScanStageKey | null;
  completedStages: ScanStageKey[];
  failed?: boolean;
}) {
  const engine = status?.engine;
  const gallery = status?.gallery;
  const done = new Set(completedStages);

  return (
    <div className="space-y-3">
      <Rail title="Engine">
        <Readout
          icon={<Cpu aria-hidden />}
          label="Model"
          value={engine?.family === "onnx-arcface" || engine?.family === "insightface-arcface"
            ? `ArcFace · ${engine?.pack ?? "512-d"}`
            : engine?.family ?? "unavailable"}
          tone={engine?.biometric ? "default" : "warn"}
          hint={engine?.biometric
            ? undefined
            : "Degraded mode — compares photos, not faces."}
        />
        <Readout
          icon={<Gauge aria-hidden />}
          label="Match threshold"
          value={engine?.recommended_threshold != null
            ? similarityPct(engine.recommended_threshold)
            : "—"}
          hint="Below this, a hit is reported as not a match."
        />
        <Readout
          icon={<Database aria-hidden />}
          label="Records searched"
          value={gallery
            ? `${gallery.person_count.toLocaleString()} people · ${gallery.face_count.toLocaleString()} photos`
            : "—"}
        />
        {engine?.providers?.length ? (
          <Readout
            icon={<ShieldCheck aria-hidden />}
            label="Compute"
            value={engine.providers[0].replace("ExecutionProvider", "")}
            tone="dim"
          />
        ) : null}
      </Rail>

      <Rail title="Pipeline">
        <ol className="space-y-1.5">
          {SCAN_STAGES.map((s, i) => {
            const isDone = done.has(s.key);
            const isActive = activeStage === s.key;
            const isFailed = failed && isActive;
            return (
              <li
                key={s.key}
                className={cn(
                  "flex items-center gap-2 text-12 animate-face-tick",
                  isFailed ? "text-severity-high"
                    : isActive ? "text-content"
                      : isDone ? "text-content-dim" : "text-content-dim/50",
                )}
                style={{ animationDelay: `${i * 40}ms` }}
              >
                <span className="[&_svg]:size-3.5">
                  {isFailed ? <AlertTriangle aria-hidden />
                    : isDone ? <Check aria-hidden />
                      : isActive ? <Loader2 className="animate-spin" aria-hidden />
                        : <CircleDashed aria-hidden />}
                </span>
                <span className="truncate">{s.label}</span>
              </li>
            );
          })}
        </ol>
      </Rail>
    </div>
  );
}

/** Right rail — what the detector actually found, and the top score. */
export function FaceDetectionRail({ probe, topSimilarity, topBand, latencyMs, searched }: {
  probe?: FaceProbeInfo | null;
  topSimilarity?: number | null;
  topBand?: string | null;
  latencyMs?: number | null;
  searched?: number | null;
}) {
  const quality = probe?.quality;
  const qualityLabel = quality == null ? "—"
    : quality >= 0.7 ? `Good (${similarityPct(quality)})`
      : quality >= 0.4 ? `Fair (${similarityPct(quality)})`
        : `Poor (${similarityPct(quality)})`;

  return (
    <div className="space-y-3">
      <Rail title="Detection">
        <Readout
          icon={<ScanFace aria-hidden />}
          label="Faces found"
          value={probe ? String(probe.faces_detected) : "—"}
          hint={probe && probe.faces_detected > 1
            ? "Largest face used. Crop to one face if that is wrong."
            : undefined}
        />
        <Readout
          icon={<Target aria-hidden />}
          label="Detector confidence"
          value={probe?.detector_score != null ? similarityPct(probe.detector_score) : "—"}
        />
        <Readout
          icon={<Gauge aria-hidden />}
          label="Image quality"
          value={qualityLabel}
          tone={quality != null && quality < 0.4 ? "warn" : "default"}
          hint={quality != null && quality < 0.4
            ? "A blurred or small face weakens the match."
            : undefined}
        />
        {probe?.image_width ? (
          <Readout
            icon={<CircleDashed aria-hidden />}
            label="Frame"
            value={`${probe.image_width} x ${probe.image_height} px`}
            tone="dim"
          />
        ) : null}
      </Rail>

      <Rail title="Result">
        <Readout
          icon={<Target aria-hidden />}
          label="Best similarity"
          value={topSimilarity != null ? similarityPct(topSimilarity) : "—"}
          hint={topBand ? topBand.replace(/^\w/, (c) => c.toUpperCase()) : undefined}
        />
        <Readout
          icon={<Database aria-hidden />}
          label="Candidates returned"
          value={searched != null ? String(searched) : "—"}
          tone="dim"
        />
        <Readout
          icon={<Cpu aria-hidden />}
          label="Search time"
          value={latencyMs != null ? `${latencyMs} ms` : "—"}
          tone="dim"
        />
      </Rail>
    </div>
  );
}
