import { useEffect, useRef, useState } from "react";
import { Viewer } from "mapillary-js";
import "mapillary-js/dist/mapillary.css";
import { Camera, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  findNearestMapillaryImage,
  hasMapillary,
  MAPILLARY_TOKEN,
} from "@/components/map/mapillary";

/* ============================================================================
   Mapillary street-view panel: a floating, embedded viewer that resolves the
   nearest street-level image to a target coordinate and lets the user walk the
   street. Degrades gracefully with no token / no coverage.
   ========================================================================== */

type Status = "loading" | "ready" | "none" | "error" | "no-token";

export function StreetViewPanel({
  target,
  onClose,
  onImageLocated,
}: {
  target: { lon: number; lat: number };
  onClose: () => void;
  onImageLocated?: (lon: number, lat: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const onLocatedRef = useRef(onImageLocated);
  onLocatedRef.current = onImageLocated;
  const [status, setStatus] = useState<Status>(hasMapillary() ? "loading" : "no-token");

  // Create the viewer once.
  useEffect(() => {
    if (!hasMapillary() || !containerRef.current) return;
    let viewer: Viewer | null = null;
    try {
      viewer = new Viewer({
        accessToken: MAPILLARY_TOKEN,
        container: containerRef.current,
        component: { cover: false },
      });
      viewerRef.current = viewer;
    } catch {
      setStatus("error");
    }
    return () => {
      try {
        viewer?.remove();
      } catch {
        /* ignore */
      }
      viewerRef.current = null;
    };
  }, []);

  // Resolve the target coordinate -> nearest image -> move the viewer there.
  useEffect(() => {
    if (!hasMapillary()) return;
    const ctrl = new AbortController();
    setStatus("loading");
    findNearestMapillaryImage(target.lon, target.lat, ctrl.signal)
      .then((img) => {
        if (ctrl.signal.aborted) return;
        if (!img) {
          setStatus("none");
          return;
        }
        onLocatedRef.current?.(img.lon, img.lat);
        const v = viewerRef.current;
        if (!v) {
          setStatus("error");
          return;
        }
        v.moveTo(img.id)
          .then(() => !ctrl.signal.aborted && setStatus("ready"))
          .catch(() => !ctrl.signal.aborted && setStatus("error"));
      })
      .catch((e) => {
        if (e?.name !== "AbortError") setStatus("error");
      });
    return () => ctrl.abort();
  }, [target.lon, target.lat]);

  return (
    <div className="absolute bottom-3 right-3 z-20 flex h-72 w-[26rem] max-w-[calc(100%-1.5rem)] flex-col overflow-hidden rounded-card border border-hairline bg-surface shadow-pop">
      <div className="flex shrink-0 items-center gap-2 border-b border-hairline px-3 py-2">
        <Camera className="size-4 text-primary" />
        <span className="text-13 font-semibold text-content">Street view</span>
        <span className="tnum text-12 text-content-dim">
          {target.lat.toFixed(4)}, {target.lon.toFixed(4)}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="ml-auto rounded-control p-1 text-content-dim transition-colors hover:bg-surface-2 hover:text-content"
          aria-label="Close street view"
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="relative min-h-0 flex-1 bg-black">
        {/* mapillary-js renders into this element */}
        <div ref={containerRef} className={cn("absolute inset-0", status !== "ready" && "opacity-0")} />

        {status !== "ready" && (
          <div className="absolute inset-0 grid place-items-center p-4 text-center">
            {status === "loading" && (
              <div className="flex flex-col items-center gap-2 text-content-dim">
                <Loader2 className="size-5 animate-spin" />
                <span className="text-12">Finding nearby imagery…</span>
              </div>
            )}
            {status === "none" && (
              <div className="text-12 text-content-dim">
                No Mapillary street imagery within range of this point.
              </div>
            )}
            {status === "error" && (
              <div className="text-12 text-content-dim">Couldn't load street imagery here.</div>
            )}
            {status === "no-token" && (
              <div className="max-w-xs text-12 text-content-dim">
                Set <code className="rounded bg-surface-2 px-1">VITE_MAPILLARY_TOKEN</code> to enable
                embedded street view.
              </div>
            )}
          </div>
        )}
      </div>

      <div className="shrink-0 border-t border-hairline px-3 py-1.5 text-[11px] text-content-dim">
        Imagery © Mapillary contributors · click the map to move the camera
      </div>
    </div>
  );
}
