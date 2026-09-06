/* Browser-side image preparation for facial recognition.

   The probe travels as base64 inside a JSON body, so the raw file is the wrong
   thing to send: a modern phone photo is 3-6 MB and the server's probe cap is
   ~1.2 MB. Downscaling here is not just about the limit — a 4000px frame costs
   real detector latency for no accuracy gain, because the detector runs at a
   fixed 640px input anyway. Resizing to ~1280px and re-encoding as JPEG q0.82
   typically lands at 120-250 KB and makes the scan feel instant.

   Everything is Canvas + WebCrypto: no dependencies, and the bytes never leave
   the page except through the one API call the user asked for. */

export interface PreparedImage {
  /** Bare base64 (no data-URL prefix) — what the API expects. */
  base64: string;
  /** Data URL for the on-screen preview. */
  dataUrl: string;
  bytes: number;
  width: number;
  height: number;
  mimeType: string;
  /** True when the source was resized to fit the long-edge budget. */
  resized: boolean;
}

export const ACCEPTED_IMAGE_TYPES = [
  "image/jpeg", "image/png", "image/webp", "image/bmp",
] as const;

const DEFAULT_LONG_EDGE = 1280;
const DEFAULT_QUALITY = 0.82;
/** Below this the JPEG gets blocky enough to cost real matching accuracy. */
const MIN_QUALITY = 0.55;
/** A face smaller than this in the source is unlikely to encode usefully. */
export const MIN_USEFUL_EDGE = 160;

export class FaceCaptureError extends Error {}

function stripDataUrl(dataUrl: string): string {
  const comma = dataUrl.indexOf(",");
  return comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
}

/** Approximate decoded byte length of a base64 string (no allocation). */
export function base64Bytes(base64: string): number {
  const len = base64.length;
  if (!len) return 0;
  let padding = 0;
  if (base64.endsWith("==")) padding = 2;
  else if (base64.endsWith("=")) padding = 1;
  return Math.floor((len * 3) / 4) - padding;
}

async function loadBitmap(source: Blob): Promise<{
  draw: CanvasImageSource;
  width: number;
  height: number;
  release: () => void;
}> {
  // createImageBitmap honours EXIF orientation with imageOrientation: "from-image",
  // which matters: an unrotated portrait photo hides the face from the detector.
  if (typeof createImageBitmap === "function") {
    try {
      const bitmap = await createImageBitmap(source, { imageOrientation: "from-image" });
      return {
        draw: bitmap, width: bitmap.width, height: bitmap.height,
        release: () => bitmap.close(),
      };
    } catch {
      /* fall through to <img> */
    }
  }
  const url = URL.createObjectURL(source);
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = () => reject(new FaceCaptureError("That image could not be decoded."));
      el.src = url;
    });
    return {
      draw: img, width: img.naturalWidth, height: img.naturalHeight,
      release: () => URL.revokeObjectURL(url),
    };
  } catch (e) {
    URL.revokeObjectURL(url);
    throw e;
  }
}

function drawToCanvas(
  draw: CanvasImageSource, srcW: number, srcH: number, longEdge: number,
): { canvas: HTMLCanvasElement; width: number; height: number; resized: boolean } {
  const scale = Math.min(1, longEdge / Math.max(srcW, srcH));
  const width = Math.max(1, Math.round(srcW * scale));
  const height = Math.max(1, Math.round(srcH * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new FaceCaptureError("This browser could not process the image.");
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(draw, 0, 0, width, height);
  return { canvas, width, height, resized: scale < 1 };
}

function canvasToDataUrl(canvas: HTMLCanvasElement, quality: number): string {
  return canvas.toDataURL("image/jpeg", quality);
}

export interface PrepareOptions {
  /** Server's advertised long edge (FaceStatusResponse.recommended_long_edge). */
  longEdge?: number;
  /** Server's probe cap (FaceStatusResponse.max_image_bytes). */
  maxBytes?: number;
}

/** Decode, EXIF-correct, downscale and JPEG-encode an image for the face API.
 *
 *  Re-encodes at a lower quality (then a smaller edge) until it fits `maxBytes`,
 *  and gives up with a readable error rather than shipping something the server
 *  will reject. */
export async function prepareFaceImage(
  source: Blob, opts: PrepareOptions = {},
): Promise<PreparedImage> {
  const longEdge = Math.max(320, opts.longEdge ?? DEFAULT_LONG_EDGE);
  const maxBytes = Math.max(64_000, opts.maxBytes ?? 1_200_000);

  if (source.size === 0) throw new FaceCaptureError("That file is empty.");
  if (source.type && !ACCEPTED_IMAGE_TYPES.includes(source.type as never)) {
    throw new FaceCaptureError(
      `${source.type} is not a supported image type. Use a JPEG, PNG or WebP photo.`);
  }

  const { draw, width: srcW, height: srcH, release } = await loadBitmap(source);
  try {
    if (Math.max(srcW, srcH) < MIN_USEFUL_EDGE) {
      throw new FaceCaptureError(
        `That image is only ${srcW}x${srcH}px — too small to read a face from. ` +
        `Use an image at least ${MIN_USEFUL_EDGE}px on its long edge.`);
    }
    let edge = longEdge;
    let resizedFlag = false;
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const { canvas, width, height, resized } = drawToCanvas(draw, srcW, srcH, edge);
      resizedFlag = resized || resizedFlag;
      let quality = DEFAULT_QUALITY;
      let dataUrl = canvasToDataUrl(canvas, quality);
      let base64 = stripDataUrl(dataUrl);
      while (base64Bytes(base64) > maxBytes && quality > MIN_QUALITY) {
        quality = Math.max(MIN_QUALITY, quality - 0.1);
        dataUrl = canvasToDataUrl(canvas, quality);
        base64 = stripDataUrl(dataUrl);
      }
      if (base64Bytes(base64) <= maxBytes) {
        return {
          base64, dataUrl, bytes: base64Bytes(base64),
          width, height, mimeType: "image/jpeg", resized: resizedFlag,
        };
      }
      edge = Math.round(edge * 0.75);       // still too big: shrink and retry
      if (edge < MIN_USEFUL_EDGE) break;
    }
    throw new FaceCaptureError(
      "That image could not be compressed small enough to scan. Try a smaller photo.");
  } finally {
    release();
  }
}

/** Grab the current frame from a playing <video> and prepare it as a probe. */
export async function captureFromVideo(
  video: HTMLVideoElement, opts: PrepareOptions = {},
): Promise<PreparedImage> {
  const w = video.videoWidth;
  const h = video.videoHeight;
  if (!w || !h) {
    throw new FaceCaptureError("The camera is not ready yet. Wait for the preview.");
  }
  const frame = document.createElement("canvas");
  frame.width = w;
  frame.height = h;
  const ctx = frame.getContext("2d");
  if (!ctx) throw new FaceCaptureError("This browser could not read the camera frame.");
  ctx.drawImage(video, 0, 0, w, h);
  const blob = await new Promise<Blob | null>((resolve) =>
    frame.toBlob(resolve, "image/jpeg", 0.95));
  if (!blob) throw new FaceCaptureError("The camera frame could not be captured.");
  return prepareFaceImage(blob, opts);
}

/** True when this browser/context can open a camera. Camera access requires a
 *  secure context, so this is false on plain http:// (except localhost). */
export function cameraSupported(): boolean {
  return (
    typeof navigator !== "undefined"
    && !!navigator.mediaDevices?.getUserMedia
    && (typeof window === "undefined" || window.isSecureContext !== false)
  );
}

/** Turn a getUserMedia rejection into something an officer can act on. */
export function describeCameraError(err: unknown): string {
  const name = (err as { name?: string } | null)?.name ?? "";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Camera access was blocked. Allow camera permission for this site, "
        + "then try again — or upload a photo instead.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No camera was found on this device. Upload a photo instead.";
    case "NotReadableError":
      return "The camera is in use by another application. Close it and try again.";
    case "AbortError":
      return "Starting the camera was interrupted. Try again.";
    default:
      if (!cameraSupported()) {
        return "This browser cannot open a camera here. Camera capture needs an "
          + "HTTPS connection (or localhost). Upload a photo instead.";
      }
      return (err as Error | null)?.message || "The camera could not be started.";
  }
}

/** A human byte size for capture UI, e.g. 214 KB. */
export function formatImageBytes(n?: number | null): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  const kb = n / 1024;
  return kb < 1024 ? `${Math.round(kb)} KB` : `${(kb / 1024).toFixed(1)} MB`;
}
