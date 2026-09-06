import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Camera, CameraOff, CheckCircle2, ImageUp, Info, Loader2,
  RotateCcw, ShieldAlert, Star, SwitchCamera, Trash2, UserRoundCheck,
} from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  FaceCaptureError, captureFromVideo, formatImageBytes, prepareFaceImage,
  type PreparedImage,
} from "@/lib/faceCapture";
import { FaceScanViewport } from "./FaceScanViewport";
import { similarityPct, useFaceStatus, usePersonFaces, usePrefersReducedMotion } from "./faceShared";
import { useCamera } from "./useCamera";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canonicalPersonId: number;
  personLabel?: string | null;
}

/** Add or retire a person's reference photos — the gallery every face search is
 *  matched against.
 *
 *  A reference photo is the highest-leverage input in the whole feature: a blurred
 *  or badly cropped one produces false matches for *everyone*, not just this
 *  person. So the server enforces a quality floor and this dialog surfaces the
 *  measured quality rather than silently accepting whatever was uploaded. */
export function FaceEnrolDialog({
  open, onOpenChange, canonicalPersonId, personLabel,
}: Props) {
  const qc = useQueryClient();
  const statusQ = useFaceStatus(open);
  const facesQ = usePersonFaces(open ? canonicalPersonId : null);
  const camera = useCamera();
  const reducedMotion = usePrefersReducedMotion();

  const [image, setImage] = useState<PreparedImage | null>(null);
  const [label, setLabel] = useState("");
  const [makePrimary, setMakePrimary] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);

  const status = statusQ.data;
  const engineReady = !!status?.enabled && !!status?.available;
  const degraded = !!status?.engine && !status.engine.biometric;
  const faces = facesQ.data?.faces ?? [];
  const limit = status?.max_gallery_per_person ?? 8;
  const atLimit = faces.filter((f) => !f.is_archived).length >= limit;

  const prepOpts = {
    longEdge: status?.recommended_long_edge,
    maxBytes: status?.max_image_bytes,
  };

  const accept = async (blob: Blob) => {
    setError(null);
    setDone(null);
    setWarnings([]);
    try {
      setImage(await prepareFaceImage(blob, prepOpts));
      camera.stop();
    } catch (e) {
      setError(e instanceof FaceCaptureError ? e.message : errorMessage(e));
    }
  };

  const shoot = async () => {
    const video = camera.videoRef.current;
    if (!video) return;
    try {
      setImage(await captureFromVideo(video, prepOpts));
      camera.stop();
    } catch (e) {
      setError(e instanceof FaceCaptureError ? e.message : errorMessage(e));
    }
  };

  const reset = () => {
    setImage(null);
    setLabel("");
    setMakePrimary(false);
    setError(null);
    setDone(null);
    setWarnings([]);
    camera.stop();
  };

  const save = async () => {
    if (!image) return;
    setBusy(true);
    setError(null);
    setWarnings([]);
    try {
      const res = await api.face.enrol({
        image_base64: image.base64,
        canonical_person_id: canonicalPersonId,
        image_label: label.trim() || undefined,
        make_primary: makePrimary,
        capture_mode: camera.state !== "idle" ? "camera" : "upload",
      });
      setDone(
        res.created
          ? `Reference photo added (quality ${similarityPct(res.quality)}). `
            + `${res.gallery_face_count} of ${limit} photos on file.`
          : "That photo was already enrolled for this person.",
      );
      setWarnings(res.warnings);
      setImage(null);
      setLabel("");
      setMakePrimary(false);
      qc.invalidateQueries({ queryKey: ["face"] });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const retire = async (faceId: number) => {
    setBusy(true);
    setError(null);
    try {
      await api.face.removeFace(faceId, "retired from the person record");
      qc.invalidateQueries({ queryKey: ["face"] });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Reference photos</DialogTitle>
          <DialogDescription>
            Photos enrolled here are what a face scan is matched against.
            {personLabel ? ` Adding to ${personLabel}.` : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[70vh] space-y-3 overflow-y-auto pr-1">
          {!engineReady && (
            <div className="flex items-start gap-2 rounded-card border border-severity-high/40 bg-severity-high/5 p-3 text-12">
              <ShieldAlert className="mt-0.5 size-4 shrink-0 text-severity-high" aria-hidden />
              <div>
                <p className="font-bold text-severity-high">Face engine unavailable</p>
                <p className="mt-0.5 text-content-dim">
                  {status?.unavailable_reason ?? "No face engine is configured."}
                  {status?.models?.install_command && (
                    <>
                      {" "}Run{" "}
                      <code className="rounded-badge bg-surface-2 px-1 py-0.5 font-mono text-11">
                        {status.models.install_command}
                      </code>{" "}on the server.
                    </>
                  )}
                </p>
              </div>
            </div>
          )}
          {engineReady && degraded && (
            <div className="flex items-start gap-2 rounded-card border border-severity-medium/40 bg-severity-medium/5 p-3 text-12">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-severity-medium" aria-hidden />
              <p className="text-content-dim">
                <span className="font-bold text-severity-medium">Degraded mode.</span>{" "}
                The fallback backend stores an image fingerprint, not a face descriptor,
                so these photos will only ever match the identical file.
              </p>
            </div>
          )}

          {/* --- existing gallery --- */}
          <section className="rounded-card border border-hairline bg-surface-2/40 p-3">
            <div className="mb-2 flex items-center justify-between">
              <h4 className="text-11 font-bold uppercase tracking-wider text-content-dim">
                On file
              </h4>
              <span className="tnum text-11 text-content-dim">
                {faces.filter((f) => !f.is_archived).length} / {limit}
              </span>
            </div>
            {facesQ.isLoading ? (
              <p className="flex items-center gap-1.5 text-12 text-content-dim">
                <Loader2 className="size-3.5 animate-spin" aria-hidden /> Loading…
              </p>
            ) : faces.length === 0 ? (
              <p className="text-12 text-content-dim">
                No reference photos yet. This person cannot be found by a face scan
                until at least one is added.
              </p>
            ) : (
              <ul className="divide-y divide-hairline">
                {faces.map((f) => (
                  <li
                    key={f.person_face_embedding_id}
                    className="flex flex-wrap items-center justify-between gap-2 py-1.5 text-12"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      {f.is_primary && (
                        <Badge variant="primary" className="gap-1">
                          <Star className="size-3" aria-hidden /> Reference
                        </Badge>
                      )}
                      <span className="truncate text-content">
                        {f.image_label || f.image_sha256.slice(0, 12)}
                      </span>
                      <Badge variant="outline" className="capitalize">
                        {f.enrolment_source.replace(/_/g, " ")}
                      </Badge>
                      {f.quality_score != null && (
                        <span
                          className={cn(
                            "tnum",
                            f.quality_score >= 0.6 ? "text-severity-low"
                              : f.quality_score >= 0.4 ? "text-severity-medium"
                                : "text-severity-high",
                          )}
                        >
                          quality {similarityPct(f.quality_score)}
                        </span>
                      )}
                    </span>
                    <span className="flex items-center gap-2 text-content-dim">
                      <span className="tnum">{f.created_at?.slice(0, 10) ?? "—"}</span>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        disabled={busy}
                        onClick={() => void retire(f.person_face_embedding_id)}
                        aria-label={`Retire reference photo ${f.image_label || f.person_face_embedding_id}`}
                      >
                        <Trash2 />
                      </Button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* --- add a photo --- */}
          <section className="grid gap-3 sm:grid-cols-[minmax(0,18rem)_minmax(0,1fr)]">
            <FaceScanViewport
              phase={camera.isLive || camera.state === "starting" ? "camera"
                : image ? "still" : "empty"}
              imageUrl={image?.dataUrl}
              videoRef={camera.videoRef}
              mirrored={camera.facingMode === "user"}
              reducedMotion={reducedMotion}
            />
            <div className="space-y-3">
              <input
                ref={fileInput}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/bmp"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void accept(f);
                }}
              />
              <div className="flex flex-wrap gap-2">
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
                      <CameraOff /> Stop
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void camera.start()}
                      disabled={!camera.supported || camera.state === "starting"}
                    >
                      {camera.state === "starting"
                        ? <Loader2 className="animate-spin" /> : <Camera />}
                      Use camera
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => fileInput.current?.click()}
                    >
                      <ImageUp /> Choose photo
                    </Button>
                  </>
                )}
              </div>

              <label className="block space-y-1">
                <span className="text-12 font-medium text-content-dim">
                  Label (optional)
                </span>
                <Input
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="e.g. arrest photo 2024"
                  className="h-8"
                  maxLength={160}
                />
              </label>

              <label className="flex items-center gap-2 text-12 text-content">
                <input
                  type="checkbox"
                  checked={makePrimary}
                  onChange={(e) => setMakePrimary(e.target.checked)}
                  className="size-3.5 accent-[var(--primary)]"
                />
                Use as this person's reference photo
              </label>

              {image && (
                <p className="tnum text-11 text-content-dim">
                  {image.width}x{image.height} · {formatImageBytes(image.bytes)}
                  {image.resized && " · resized for upload"}
                </p>
              )}
              {atLimit && (
                <p className="flex items-start gap-1.5 text-12 text-severity-medium">
                  <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                  This person already has {limit} photos. Retire one before adding
                  another — an over-represented person crowds out other matches.
                </p>
              )}
              {error && (
                <p className="flex items-start gap-1.5 text-12 text-severity-high" role="alert">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                  {error}
                </p>
              )}
              {warnings.map((w) => (
                <p key={w} className="flex items-start gap-1.5 text-12 text-severity-medium">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                  {w}
                </p>
              ))}
              {done && (
                <p className="flex items-start gap-1.5 text-12 text-severity-low">
                  <CheckCircle2 className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                  {done}
                </p>
              )}

              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  onClick={() => void save()}
                  disabled={!image || busy || !engineReady || atLimit}
                >
                  {busy
                    ? <><Loader2 className="animate-spin" /> Saving…</>
                    : <><UserRoundCheck /> Add reference photo</>}
                </Button>
                {image && (
                  <Button variant="ghost" size="sm" onClick={reset} disabled={busy}>
                    <RotateCcw /> Clear
                  </Button>
                )}
              </div>
            </div>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
