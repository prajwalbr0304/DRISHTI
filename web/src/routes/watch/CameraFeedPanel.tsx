import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, Maximize2, Minimize2, Video, VideoOff, Volume2, VolumeX, X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { CctvBox, CctvCamera } from "@/api/endpoints/cctv";
import { severityHex } from "@/routes/watch/cctvLayers";
import { formatAge } from "@/routes/watch/cctvFormat";

/* ============================================================================
   A single live camera tile, modelled on the Mapillary StreetViewPanel shell:
   header + black media area + attribution/status footer, with every playback
   state named explicitly.

   The honesty rules this component enforces:

     * `stream_kind: "none"` renders a clearly-labelled NO-SIGNAL panel naming the
       setting that would enable imagery. It never shows a placeholder graphic
       that could be mistaken for a live picture.
     * an offline / maintenance camera shows NO media at all, even if a stream URL
       happens to be set, because the estate has told us it is not being watched.
     * HLS needs native browser support (there is no hls.js in this project).
       Chrome/Firefox cannot play `.m3u8` natively, so instead of a silent black
       rectangle the panel says exactly that and offers the URL.
     * the detection overlay is drawn from normalised [0,1] boxes and is always
       captioned with the class label + score, so a box is never a bare
       accusation floating over a person.
   ========================================================================== */

type PlaybackState = "no-stream" | "not-watched" | "loading" | "ready" | "error" | "unsupported";

function canPlayHls(): boolean {
  if (typeof document === "undefined") return false;
  const v = document.createElement("video");
  return Boolean(
    v.canPlayType("application/vnd.apple.mpegurl")
    || v.canPlayType("application/x-mpegURL"),
  );
}

export function CameraFeedPanel({
  camera,
  boxes,
  detectorKind,
  severity,
  detectionLabel,
  ageSeconds,
  onClose,
  onOpenDetail,
  className,
  showOverlay = true,
}: {
  camera: CctvCamera;
  /** Normalised detection boxes to overlay, when this tile is showing an alert. */
  boxes?: CctvBox[];
  /** Which detector produced `boxes`. Gates the overlay — see below. */
  detectorKind?: string | null;
  severity?: string | null;
  detectionLabel?: string | null;
  ageSeconds?: number | null;
  onClose: () => void;
  onOpenDetail?: () => void;
  className?: string;
  showOverlay?: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [muted, setMuted] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const dark = camera.status === "offline" || camera.status === "maintenance";
  const hasStream = camera.stream_kind !== "none" && Boolean(camera.stream_url);
  const hlsUnsupported = camera.stream_kind === "hls" && !canPlayHls();

  const initialState: PlaybackState = dark
    ? "not-watched"
    : !hasStream
      ? "no-stream"
      : hlsUnsupported
        ? "unsupported"
        : "loading";
  const [state, setState] = useState<PlaybackState>(initialState);

  // Reset playback state when the tile is pointed at a different camera.
  useEffect(() => setState(initialState), [initialState, camera.camera_id]);

  useEffect(() => {
    const v = videoRef.current;
    if (v) v.muted = muted;
  }, [muted]);

  const isVideo = camera.stream_kind === "hls" || camera.stream_kind === "mp4_loop";
  const isSnapshot = camera.stream_kind === "image_snapshot";
  const accent = severity ? severityHex(severity) : undefined;

  // A SYNTHETIC detection's box coordinates are generated, not measured — they
  // have no relationship to the pixels in a real clip. Drawing them anyway put
  // "person 88%" rectangles on empty pavement while the actual people stood
  // elsewhere in frame, which is not a cosmetic glitch: a box over real footage
  // is a specific claim about a specific person at that spot. So the overlay is
  // drawn ONLY for detections measured from these frames by real analytics.
  const boxesAreMeasured = detectorKind === "external_analytics";
  const overlayBoxes = useMemo(
    () => (showOverlay && boxesAreMeasured ? (boxes ?? []).slice(0, 24) : []),
    [boxes, showOverlay, boxesAreMeasured],
  );
  const overlaySuppressed = Boolean(
    showOverlay && !boxesAreMeasured && (boxes?.length ?? 0) > 0,
  );

  return (
    <div
      className={cn(
        "flex flex-col overflow-hidden rounded-card border bg-surface shadow-pop",
        accent ? "border-transparent" : "border-hairline",
        expanded ? "h-[28rem] w-[42rem]" : "h-64 w-[24rem]",
        "max-w-[calc(100vw-2rem)]",
        className,
      )}
      style={accent ? { borderColor: accent } : undefined}
    >
      {/* header */}
      <div className="flex shrink-0 items-center gap-2 border-b border-hairline px-3 py-2">
        {dark ? (
          <VideoOff className="size-4 shrink-0 text-content-dim" />
        ) : (
          <Video className="size-4 shrink-0 text-primary" />
        )}
        <button
          type="button"
          onClick={onOpenDetail}
          disabled={!onOpenDetail}
          className={cn(
            "min-w-0 truncate text-13 font-semibold text-content",
            onOpenDetail && "hover:text-primary hover:underline",
          )}
          title={camera.location_label || camera.name}
        >
          {camera.name}
        </button>
        <span className="shrink-0 font-mono text-11 text-content-dim">{camera.code}</span>

        <div className="ml-auto flex shrink-0 items-center gap-1">
          {state === "ready" && (
            <span className="flex items-center gap-1 text-11 font-bold uppercase text-severity-critical">
              <span className="size-1.5 rounded-full bg-severity-critical animate-redzone-pulse" />
              live
            </span>
          )}
          {isVideo && state === "ready" && (
            <button
              type="button"
              onClick={() => setMuted((m) => !m)}
              className="rounded-control p-1 text-content-dim transition-colors hover:bg-surface-2 hover:text-content"
              aria-label={muted ? `Unmute ${camera.name}` : `Mute ${camera.name}`}
            >
              {muted ? <VolumeX className="size-3.5" /> : <Volume2 className="size-3.5" />}
            </button>
          )}
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="rounded-control p-1 text-content-dim transition-colors hover:bg-surface-2 hover:text-content"
            aria-label={expanded ? `Shrink ${camera.name} feed` : `Enlarge ${camera.name} feed`}
          >
            {expanded ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-control p-1 text-content-dim transition-colors hover:bg-surface-2 hover:text-content"
            aria-label={`Close ${camera.name} feed`}
          >
            <X className="size-4" />
          </button>
        </div>
      </div>

      {/* media */}
      <div className="relative min-h-0 flex-1 bg-black">
        {isVideo && !dark && hasStream && !hlsUnsupported && (
          <video
            ref={videoRef}
            className={cn("absolute inset-0 size-full object-cover",
              state !== "ready" && "opacity-0")}
            src={camera.stream_url ?? undefined}
            poster={camera.poster_url ?? undefined}
            autoPlay
            loop={camera.stream_kind === "mp4_loop"}
            muted={muted}
            playsInline
            preload="metadata"
            onCanPlay={() => setState("ready")}
            onError={() => setState("error")}
          >
            <track kind="captions" label="No captions available" />
          </video>
        )}

        {isSnapshot && !dark && hasStream && (
          <img
            className={cn("absolute inset-0 size-full object-cover",
              state !== "ready" && "opacity-0")}
            src={camera.stream_url ?? undefined}
            alt={`Latest snapshot from ${camera.name}`}
            onLoad={() => setState("ready")}
            onError={() => setState("error")}
          />
        )}

        {/* detection overlay — normalised boxes, always captioned */}
        {state === "ready" && overlayBoxes.length > 0 && (
          <div className="pointer-events-none absolute inset-0" aria-hidden="true">
            {overlayBoxes.map((b, i) => (
              <div
                key={`${b.x}-${b.y}-${i}`}
                className="absolute rounded-[3px] border-2"
                style={{
                  left: `${b.x * 100}%`,
                  top: `${b.y * 100}%`,
                  width: `${b.w * 100}%`,
                  height: `${b.h * 100}%`,
                  borderColor: accent ?? "#f97316",
                  boxShadow: "0 0 0 1px rgba(0,0,0,.45)",
                }}
              >
                <span
                  className="absolute -top-4 left-0 whitespace-nowrap rounded-sm px-1 text-[10px] font-bold text-white"
                  style={{ background: accent ?? "#f97316" }}
                >
                  {b.label ?? "object"}
                  {b.score != null && ` ${Math.round(b.score * 100)}%`}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* incident caption strip */}
        {detectionLabel && (
          <div className="absolute inset-x-0 bottom-0 flex items-center gap-2 bg-gradient-to-t from-black/85 to-transparent px-3 pb-2 pt-6">
            <span className="truncate text-12 font-bold text-white">{detectionLabel}</span>
            {ageSeconds != null && (
              <span className="ml-auto shrink-0 text-11 text-white/70">
                {formatAge(ageSeconds)}
              </span>
            )}
          </div>
        )}

        {/* Explicit non-playing states. The media area is ALWAYS black, so this
            copy uses fixed light colours rather than the theme's `content`
            tokens — those are near-black in the light "desk" theme and would be
            unreadable here. Extra bottom padding keeps the block clear of the
            incident caption strip. */}
        {state !== "ready" && (
          <div className={cn("absolute inset-0 grid place-items-center px-4 py-3 text-center",
            detectionLabel && "pb-10")}>
            {state === "loading" && (
              <div className="flex flex-col items-center gap-2 text-white/75">
                <Video className="size-5 animate-pulse" />
                <span className="text-12">Connecting to feed…</span>
              </div>
            )}
            {state === "not-watched" && (
              <div className="max-w-[17rem] space-y-1">
                <VideoOff className="mx-auto size-5 text-white/60" />
                <p className="text-12 font-semibold text-white">
                  Camera {camera.status}
                </p>
                <p className="text-11 leading-snug text-white/70">
                  Not producing frames, so it is not being analysed. No alert can
                  originate here.
                </p>
              </div>
            )}
            {state === "no-stream" && (
              <div className="max-w-[18rem] space-y-1">
                <VideoOff className="mx-auto size-5 text-white/60" />
                <p className="text-12 font-semibold text-white">No stream configured</p>
                <p className="text-11 leading-snug text-white/70">
                  Registered with a position but no imagery. Set{" "}
                  <code className="rounded bg-white/15 px-1 text-white/90">CCTV_DEMO_STREAM_URL</code>,
                  or give the camera a{" "}
                  <code className="rounded bg-white/15 px-1 text-white/90">stream_url</code>.
                </p>
              </div>
            )}
            {state === "unsupported" && (
              <div className="max-w-[18rem] space-y-1">
                <AlertTriangle className="mx-auto size-5 text-severity-high" />
                <p className="text-12 font-semibold text-white">
                  HLS not supported by this browser
                </p>
                <p className="text-11 leading-snug text-white/70">
                  This build ships no HLS player. Safari plays HLS natively;
                  elsewhere use an{" "}
                  <code className="rounded bg-white/15 px-1 text-white/90">mp4_loop</code> source.
                </p>
              </div>
            )}
            {state === "error" && (
              <div className="max-w-[18rem] space-y-1">
                <AlertTriangle className="mx-auto size-5 text-severity-high" />
                <p className="text-12 font-semibold text-white">Feed unavailable</p>
                <p className="text-11 leading-snug text-white/70">
                  The configured stream could not be loaded. The camera record and
                  its alerts are unaffected.
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* footer */}
      <div className="flex shrink-0 items-center gap-2 border-t border-hairline px-3 py-1.5">
        <span
          className="truncate text-[11px] text-content-dim"
          title={overlaySuppressed
            ? "This detection's bounding boxes were generated, not measured from "
              + "these frames, so drawing them over the video would place a claim on "
              + "whoever happens to be standing there. The detected class and count "
              + "are still shown on the review card."
            : undefined}
        >
          {overlaySuppressed
            ? "Overlay off — boxes not measured from these frames"
            : camera.location_label
              || `${camera.lat.toFixed(4)}, ${camera.lon.toFixed(4)}`}
        </span>
        <div className="ml-auto flex shrink-0 items-center gap-1">
          {!camera.analytics_enabled && !dark && (
            <Badge variant="outline">analytics off</Badge>
          )}
          {camera.status === "degraded" && <Badge variant="medium">degraded</Badge>}
        </div>
      </div>
    </div>
  );
}
