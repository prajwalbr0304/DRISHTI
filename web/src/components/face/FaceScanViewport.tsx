import { useMemo } from "react";
import { ScanFace, VideoOff } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FaceProbeInfo } from "@/api/types";

/** The scan stage the viewport should render. */
export type ViewportPhase = "empty" | "camera" | "still" | "scanning" | "result";

interface Props {
  phase: ViewportPhase;
  /** Data URL of the captured/selected still. */
  imageUrl?: string | null;
  videoRef?: React.RefObject<HTMLVideoElement>;
  /** Mirror the preview for a front-facing camera so it reads like a mirror. */
  mirrored?: boolean;
  /** Detector output — drives the lock-on bracket + landmark dots. */
  probe?: FaceProbeInfo | null;
  reducedMotion?: boolean;
  /** Tint the lock-on bracket by outcome. */
  outcome?: "match" | "possible" | "none" | null;
  className?: string;
}

/** Percentage geometry for the detected face box, relative to the source image. */
function boxPercent(probe?: FaceProbeInfo | null) {
  if (!probe?.image_width || !probe?.image_height) return null;
  const { x = 0, y = 0, w = 0, h = 0 } = probe.bounding_box ?? {};
  if (!w || !h) return null;
  const iw = probe.image_width;
  const ih = probe.image_height;
  // Pad slightly so the bracket frames the face instead of cropping the jaw.
  const padX = w * 0.08;
  const padY = h * 0.08;
  const left = Math.max(0, (x - padX) / iw) * 100;
  const top = Math.max(0, (y - padY) / ih) * 100;
  const width = Math.min(100 - left, ((w + padX * 2) / iw) * 100);
  const height = Math.min(100 - top, ((h + padY * 2) / ih) * 100);
  return { left, top, width, height };
}

const OUTCOME_STROKE: Record<string, string> = {
  match: "border-severity-low",
  possible: "border-severity-medium",
  none: "border-content-dim",
};

/** The scan stage: image or live camera, with the alignment grid, the sweeping
 *  scan line while work is in flight, and a lock-on bracket over the detected
 *  face once the detector has reported.
 *
 *  The overlay is purely decorative — every fact it hints at (face found,
 *  quality, match band) is also written as text in the rails beside it, so the
 *  graphics can be dropped under prefers-reduced-motion without losing anything. */
export function FaceScanViewport({
  phase, imageUrl, videoRef, mirrored, probe, reducedMotion, outcome, className,
}: Props) {
  const box = useMemo(() => boxPercent(probe), [probe]);
  const showLock = phase === "result" && !!box;
  const scanning = phase === "scanning";

  return (
    <div
      className={cn(
        "relative aspect-[4/3] w-full overflow-hidden rounded-card border border-hairline bg-bg",
        className,
      )}
    >
      {/* --- media layer --- */}
      {phase === "camera" ? (
        <video
          ref={videoRef}
          muted
          playsInline
          autoPlay
          aria-label="Live camera preview"
          className={cn("size-full object-cover", mirrored && "scale-x-[-1]")}
        />
      ) : imageUrl ? (
        <img
          src={imageUrl}
          alt="Photo being checked against person records"
          className="size-full object-contain"
        />
      ) : (
        <div className="flex size-full flex-col items-center justify-center gap-2 text-content-dim">
          {phase === "empty" ? (
            <ScanFace className="size-9" aria-hidden />
          ) : (
            <VideoOff className="size-9" aria-hidden />
          )}
          <p className="text-13">No image yet</p>
        </div>
      )}

      {/* --- alignment grid: static, helps the user centre a face --- */}
      {(phase === "camera" || scanning) && (
        <div aria-hidden className="pointer-events-none absolute inset-0">
          <div className="absolute inset-0 opacity-[0.18]">
            <div className="absolute left-1/3 top-0 h-full w-px bg-primary" />
            <div className="absolute left-2/3 top-0 h-full w-px bg-primary" />
            <div className="absolute left-0 top-1/3 h-px w-full bg-primary" />
            <div className="absolute left-0 top-2/3 h-px w-full bg-primary" />
          </div>
          {/* framing guide for a centred head-and-shoulders shot */}
          <div className="absolute inset-x-[27%] inset-y-[12%] rounded-[42%] border border-dashed border-primary/35" />
        </div>
      )}

      {/* --- sweeping scan line: only while real work is in flight --- */}
      {scanning && !reducedMotion && (
        <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute inset-x-0 top-0 h-full animate-face-sweep">
            <div className="h-24 w-full bg-gradient-to-b from-transparent via-primary/25 to-transparent" />
            <div className="h-px w-full bg-primary shadow-[0_0_12px_2px_var(--primary)] animate-face-scanline-glow" />
          </div>
        </div>
      )}

      {/* --- viewport corner brackets (always on, static) --- */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        {(
          [
            "left-2 top-2 border-l-2 border-t-2",
            "right-2 top-2 border-r-2 border-t-2",
            "left-2 bottom-2 border-b-2 border-l-2",
            "right-2 bottom-2 border-b-2 border-r-2",
          ] as const
        ).map((pos) => (
          <span key={pos} className={cn("absolute size-5 border-primary/60", pos)} />
        ))}
      </div>

      {/* --- lock-on bracket over the detected face --- */}
      {showLock && box && (
        <div
          aria-hidden
          className={cn(
            "pointer-events-none absolute rounded-control border-2",
            OUTCOME_STROKE[outcome ?? "none"] ?? "border-primary",
            !reducedMotion && "animate-face-lock",
          )}
          style={{
            left: `${box.left}%`, top: `${box.top}%`,
            width: `${box.width}%`, height: `${box.height}%`,
          }}
        >
          <span className="absolute -top-px left-1/2 h-2 w-px -translate-x-1/2 bg-current opacity-70" />
          <span className="absolute -bottom-px left-1/2 h-2 w-px -translate-x-1/2 bg-current opacity-70" />
        </div>
      )}

      {/* --- landmark dots (eyes / nose / mouth corners) --- */}
      {showLock && probe?.landmarks?.length && probe.image_width && probe.image_height ? (
        <div aria-hidden className="pointer-events-none absolute inset-0">
          {probe.landmarks.map(([lx, ly], i) => (
            <span
              key={`${lx}-${ly}-${i}`}
              className={cn(
                "absolute size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary ring-1 ring-bg",
                !reducedMotion && "animate-face-reveal",
              )}
              style={{
                left: `${(lx / probe.image_width!) * 100}%`,
                top: `${(ly / probe.image_height!) * 100}%`,
                animationDelay: reducedMotion ? undefined : `${60 * i}ms`,
              }}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
