/** DRISHTI public landing page — behaviour hooks.
 *
 *  The app ships no JS animation runtime (no framer-motion), and one marketing
 *  page is not a good reason to add one. Scroll reveal is an IntersectionObserver
 *  flipping a class; CSS owns every transition.
 *
 *  The page carries eight looping background films. Two constraints shape the
 *  hooks below. Bandwidth: a film's `src` is withheld until its panel is near
 *  the viewport, so a visitor who never scrolls downloads one film rather than
 *  eight. Accessibility: WCAG 2.2.2 requires a way to stop motion that loops
 *  past five seconds, so a single page-level switch pauses every film at once
 *  and `prefers-reduced-motion` sets its initial position.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

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
   Page-level motion switch
   ------------------------------------------------------------------------- */

export interface MotionSwitch {
  /** Films should be running. */
  on: boolean;
  /** The OS asked for reduced motion; the control explains itself differently. */
  reduced: boolean;
  toggle: () => void;
}

/** Owns the page's single motion preference.
 *
 *  Initial position follows `prefers-reduced-motion`, and the media query stays
 *  watched so flipping the OS setting mid-visit takes effect. An explicit
 *  toggle by the visitor wins until they flip the OS setting again.
 */
export function useMotionSwitch(): MotionSwitch {
  const [reduced, setReduced] = useState(prefersReducedMotion);
  const [on, setOn] = useState(() => !prefersReducedMotion());

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(REDUCED_MOTION_QUERY);

    const apply = () => {
      setReduced(query.matches);
      setOn(!query.matches);
    };

    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, []);

  const toggle = useCallback(() => setOn((value) => !value), []);

  return useMemo(() => ({ on, reduced, toggle }), [on, reduced, toggle]);
}

/* ---------------------------------------------------------------------------
   Proximity gate
   ------------------------------------------------------------------------- */

/** Latches true once the element comes within `margin` of the viewport.
 *
 *  Used to defer a film's `src` until its panel is worth downloading. One-way:
 *  a film that has been loaded is not unloaded on scroll-away, because
 *  re-downloading it would cost more than keeping it.
 */
export function useNearViewport<T extends HTMLElement>(
  margin = "60% 0px",
): [React.RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [near, setNear] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element || near) return;

    if (typeof IntersectionObserver === "undefined") {
      setNear(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setNear(true);
          observer.disconnect();
        }
      },
      { rootMargin: margin },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [margin, near]);

  return [ref, near];
}

/* ---------------------------------------------------------------------------
   Background film
   ------------------------------------------------------------------------- */

export interface Film {
  ref: React.RefObject<HTMLVideoElement>;
  /** The `src` may be attached — the panel is near enough to be worth loading. */
  armed: boolean;
  /** Video has buffered enough to paint — gates the fade-in and the loader. */
  ready: boolean;
  playing: boolean;
  onCanPlay: () => void;
  onPlay: () => void;
  onPause: () => void;
}

/** Drives one decorative background video.
 *
 *  Playback is not owned by the video element: it follows the page motion
 *  switch. When motion is off the film pauses on a chosen still frame instead of
 *  going blank, so a reduced-motion visitor still sees the composed image.
 *
 *  @param stillFrame seconds to seek to when motion is suppressed.
 *  @param armed      the panel is near the viewport, so loading is worthwhile.
 *  @param motion     the page motion switch is on.
 */
export function useFilm(stillFrame: number, armed: boolean, motion: boolean): Film {
  const ref = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    const video = ref.current;
    if (!video || !armed) return;

    if (!motion) {
      video.pause();
      // Seeking past a not-yet-known duration throws; clamp when we have one.
      if (Number.isFinite(video.duration) && video.duration > 0) {
        video.currentTime = Math.min(stillFrame, video.duration);
      }
      setPlaying(false);
      return;
    }

    // play() rejects when the browser blocks autoplay; reflect reality in the
    // control rather than claiming the film is running.
    void video
      .play()
      .then(() => setPlaying(true))
      .catch(() => setPlaying(false));
  }, [armed, motion, stillFrame, ready]);

  const onCanPlay = useCallback(() => setReady(true), []);
  const onPlay = useCallback(() => setPlaying(true), []);
  const onPause = useCallback(() => setPlaying(false), []);

  return { ref, armed, ready, playing, onCanPlay, onPlay, onPause };
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
