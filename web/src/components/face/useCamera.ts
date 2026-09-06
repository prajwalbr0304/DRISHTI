import { useCallback, useEffect, useRef, useState } from "react";
import { cameraSupported, describeCameraError } from "@/lib/faceCapture";

export type CameraState = "idle" | "starting" | "live" | "error" | "unsupported";

/** Live camera preview for on-the-spot face capture.
 *
 *  Owns the MediaStream lifecycle, because a leaked camera track leaves the
 *  recording indicator on after the dialog closes — which, for a tool that
 *  photographs people, is not a cosmetic bug. The stream is stopped on unmount,
 *  on stop(), and before any restart. */
export function useCamera() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [state, setState] = useState<CameraState>(
    cameraSupported() ? "idle" : "unsupported");
  const [error, setError] = useState<string | null>(null);
  const [facingMode, setFacingMode] = useState<"user" | "environment">("user");
  const [hasMultipleCameras, setHasMultipleCameras] = useState(false);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setState(cameraSupported() ? "idle" : "unsupported");
  }, []);

  const start = useCallback(async (mode: "user" | "environment" = facingMode) => {
    if (!cameraSupported()) {
      setState("unsupported");
      setError(describeCameraError(null));
      return false;
    }
    setError(null);
    setState("starting");
    streamRef.current?.getTracks().forEach((t) => t.stop());
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: mode,
          // Request a face-sized frame rather than max resolution: the detector
          // runs at 640px anyway, and a 4K frame only costs encode time.
          width: { ideal: 1280 },
          height: { ideal: 960 },
        },
      });
      streamRef.current = stream;
      setFacingMode(mode);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        try {
          await videoRef.current.play();
        } catch {
          /* autoplay rejection is non-fatal; the element is muted + playsInline */
        }
      }
      setState("live");
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        setHasMultipleCameras(
          devices.filter((d) => d.kind === "videoinput").length > 1);
      } catch {
        /* device labels need permission on some browsers; not required */
      }
      return true;
    } catch (err) {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setError(describeCameraError(err));
      setState("error");
      return false;
    }
  }, [facingMode]);

  const flip = useCallback(
    () => start(facingMode === "user" ? "environment" : "user"),
    [facingMode, start]);

  // Release the device on unmount — no lingering camera indicator.
  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  return {
    videoRef, state, error, facingMode, hasMultipleCameras,
    isLive: state === "live",
    supported: state !== "unsupported",
    start, stop, flip,
  };
}
