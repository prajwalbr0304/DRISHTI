/** DRISHTI public landing page — behaviour hooks.
 *
 *  The app ships no JS animation runtime (no framer-motion), and one marketing
 *  page is not a good reason to add one. Scroll reveal is an IntersectionObserver
 *  flipping a class; CSS owns every transition. Everything here degrades to
 *  "fully visible, nothing moving" when the visitor prefers reduced motion.
 */

import { useCallback, useEffect, useRef, useState } from "react";

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia(REDUCED_MOTION_QUERY).matches
  );
}

/* ---------------------------------------------------------------------------
   Scroll reveal
   ------------------------------------------------------------------------- */

/** Reveals every `[data-reveal]` descendant of the returned ref as it scrolls
 *  into view, by adding `is-revealed`. Reveal is one-way: elements are
 *  unobserved once shown, so nothing re-hides on scroll-up.
 *
 *  Under reduced motion — or if IntersectionObserver is unavailable — every
 *  target is revealed immediately on mount, so content is never gated behind
 *  motion the visitor has opted out of.
 */
export function useReveal<T extends HTMLElement>() {
  const rootRef = useRef<T>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const targets = Array.from(root.querySelectorAll<HTMLElement>("[data-reveal]"));
    if (targets.length === 0) return;

    if (prefersReducedMotion() || typeof IntersectionObserver === "undefined") {
      targets.forEach((element) => element.classList.add("is-revealed"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-revealed");
          observer.unobserve(entry.target);
        });
      },
      // Fire a little before the element is fully in view so the transition
      // finishes around the time it reaches comfortable reading position.
      { threshold: 0.1, rootMargin: "0px 0px -10% 0px" },
    );

    targets.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, []);

  return rootRef;
}

/* ---------------------------------------------------------------------------
   Sticky header state
   ------------------------------------------------------------------------- */

/** True once the page has scrolled past `threshold` px. Drives the header's
 *  transparent → solid transition and the utility-strip collapse. */
export function useScrolled(threshold = 24): boolean {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const read = () => setScrolled(window.scrollY > threshold);
    read();
    window.addEventListener("scroll", read, { passive: true });
    return () => window.removeEventListener("scroll", read);
  }, [threshold]);

  return scrolled;
}

/* ---------------------------------------------------------------------------
   Background film
   ------------------------------------------------------------------------- */

export interface Film {
  ref: React.RefObject<HTMLVideoElement>;
  /** Video has buffered enough to paint — gates the fade-in and the loader. */
  ready: boolean;
  playing: boolean;
  onCanPlay: () => void;
  onPlay: () => void;
  onPause: () => void;
  toggle: () => void;
}

/** Owns one decorative background video.
 *
 *  Autoplay is muted and looping, but reduced-motion visitors get a paused,
 *  deliberately chosen still frame instead — and the returned `toggle` backs a
 *  visible pause/play control so anyone can stop the motion. The media query is
 *  watched live, so flipping the OS setting mid-visit takes effect immediately.
 *
 *  @param stillFrame seconds to seek to when motion is suppressed.
 */
export function useFilm(stillFrame: number): Film {
  const ref = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(true);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(REDUCED_MOTION_QUERY);

    const apply = () => {
      const video = ref.current;
      if (!video) return;

      if (query.matches) {
        video.pause();
        video.currentTime = Math.min(stillFrame, video.duration || stillFrame);
        setPlaying(false);
        return;
      }

      // play() rejects when the browser blocks autoplay; reflect reality in the
      // control rather than claiming the film is running.
      void video
        .play()
        .then(() => setPlaying(true))
        .catch(() => setPlaying(false));
    };

    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, [stillFrame]);

  const toggle = useCallback(() => {
    const video = ref.current;
    if (!video) return;

    if (video.paused) {
      void video
        .play()
        .then(() => setPlaying(true))
        .catch(() => setPlaying(false));
    } else {
      video.pause();
      setPlaying(false);
    }
  }, []);

  const onCanPlay = useCallback(() => setReady(true), []);
  const onPlay = useCallback(() => setPlaying(true), []);
  const onPause = useCallback(() => setPlaying(false), []);

  return { ref, ready, playing, onCanPlay, onPlay, onPause, toggle };
}

/* ---------------------------------------------------------------------------
   Mobile menu overlay
   ------------------------------------------------------------------------- */

/** Locks background scroll and closes on Escape while an overlay is open. */
export function useOverlay(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);
}
