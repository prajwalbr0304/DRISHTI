import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ChevronDown, ShieldCheck } from "lucide-react";
import "@/routes/landing/landing.css";

const FRAME_COUNT = 96;
const CHAPTER_HEIGHT_VH = 145;
const MAX_CACHED_FRAMES = 56;
const MAX_PRELOAD_QUEUE = 40;
const MAX_PRELOAD_LOADS = 2;
const MAX_CRITICAL_LOADS = 2;
const ANCHOR_INTERVAL = 8;

type FrameTarget = {
  sequence: number;
  frame: number;
  key: string;
};

const CHAPTERS = [
  {
    step: "01 / Observe",
    title: "Intelligence begins with sight.",
    copy: "Bring cases, signals and operational context into one coherent view without replacing human judgement.",
    align: "left",
  },
  {
    step: "02 / Understand",
    title: "Turn fragmented data into explainable insight.",
    copy: "Connect evidence, entities, timelines and analytical models while preserving the source behind every conclusion.",
    align: "right",
  },
  {
    step: "03 / Connect",
    title: "One connected picture of Karnataka.",
    copy: "Explore patterns across districts and jurisdictions with a shared, map-led operational context.",
    align: "left",
  },
  {
    step: "04 / Anticipate",
    title: "See emerging risk. Verify before action.",
    copy: "Surface hotspots and unusual patterns as decision support, with confidence, provenance and review built in.",
    align: "right",
  },
  {
    step: "05 / Respond",
    title: "Move from insight to coordinated response.",
    copy: "Give field teams and supervisors a common picture for prioritisation, dispatch and accountable follow-through.",
    align: "left",
  },
  {
    step: "06 / Command",
    title: "Built for the operational command room.",
    copy: "A calm interface for cases, networks, geospatial intelligence, forecasting and governed analytical workflows.",
    align: "right",
  },
  {
    step: "07 / Govern",
    title: "Human judgement. Amplified.",
    copy: "DRISHTI is an evidence-backed intelligence and response platform for faster, more accountable decisions.",
    align: "center",
  },
] as const;

function clamp(value: number, minimum = 0, maximum = 1) {
  return Math.min(maximum, Math.max(minimum, value));
}

function frameUrl(sequence: number, frame: number) {
  return `/landing/sequence-${String(sequence + 1).padStart(2, "0")}/frame-${String(frame + 1).padStart(3, "0")}.webp`;
}

function drawCover(canvas: HTMLCanvasElement, image: HTMLImageElement) {
  const bounds = canvas.getBoundingClientRect();
  if (!bounds.width || !bounds.height || !image.naturalWidth || !image.naturalHeight) return;

  const ratio = Math.min(window.devicePixelRatio || 1, 1.75);
  const width = Math.round(bounds.width * ratio);
  const height = Math.round(bounds.height * ratio);

  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }

  const context = canvas.getContext("2d", { alpha: false });
  if (!context) return;

  const scale = Math.max(width / image.naturalWidth, height / image.naturalHeight);
  const drawnWidth = image.naturalWidth * scale;
  const drawnHeight = image.naturalHeight * scale;
  const x = (width - drawnWidth) / 2;
  const y = (height - drawnHeight) / 2;

  context.fillStyle = "#050912";
  context.fillRect(0, 0, width, height);
  context.drawImage(image, x, y, drawnWidth, drawnHeight);
}

export function LandingPage() {
  const sequenceRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const progressRef = useRef<HTMLDivElement>(null);
  const imageCache = useRef(new Map<string, HTMLImageElement>());
  const promiseCache = useRef(new Map<string, Promise<HTMLImageElement>>());
  const preloadQueue = useRef<FrameTarget[]>([]);
  const queuedPreloads = useRef(new Set<string>());
  const activePreloads = useRef(0);
  const activeCriticalLoads = useRef(0);
  const deferredFrame = useRef<FrameTarget>();
  const latestFrame = useRef({ sequence: 0, frame: 0, key: "0:0" });
  const drawnFrame = useRef({ sequence: -1, frame: -1, key: "" });
  const animationFrame = useRef<number>();
  const [activeChapter, setActiveChapter] = useState(0);
  const [ready, setReady] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);

  const trimImageCache = useCallback(() => {
    const protectedKeys = new Set([latestFrame.current.key, drawnFrame.current.key]);

    while (imageCache.current.size > MAX_CACHED_FRAMES) {
      let removed = false;

      for (const [key, image] of imageCache.current) {
        if (protectedKeys.has(key)) continue;

        imageCache.current.delete(key);
        image.onload = null;
        image.onerror = null;
        image.src = "";
        removed = true;
        break;
      }

      if (!removed) break;
    }
  }, []);

  const ensureFrame = useCallback((sequence: number, frame: number) => {
    const boundedFrame = Math.max(0, Math.min(FRAME_COUNT - 1, frame));
    const key = `${sequence}:${boundedFrame}`;
    const cached = imageCache.current.get(key);

    if (cached?.complete && cached.naturalWidth) {
      imageCache.current.delete(key);
      imageCache.current.set(key, cached);
      return Promise.resolve(cached);
    }

    const pending = promiseCache.current.get(key);
    if (pending) return pending;

    const promise = new Promise<HTMLImageElement>((resolve, reject) => {
      const image = new Image();
      image.decoding = "async";
      image.onload = () => {
        image.onload = null;
        image.onerror = null;
        imageCache.current.set(key, image);
        trimImageCache();
        resolve(image);
      };
      image.onerror = () => {
        image.onload = null;
        image.onerror = null;
        reject(new Error(`Unable to load landing frame ${key}`));
      };
      image.src = frameUrl(sequence, boundedFrame);
    });

    promiseCache.current.set(key, promise);
    void promise.then(
      () => promiseCache.current.delete(key),
      () => promiseCache.current.delete(key),
    );
    return promise;
  }, [trimImageCache]);

  const displayFrame = useCallback((target: FrameTarget, image: HTMLImageElement) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    drawCover(canvas, image);
    drawnFrame.current = target;
    canvas.dataset.renderedSequence = String(target.sequence + 1);
    canvas.dataset.renderedFrame = String(target.frame + 1);

    if (imageCache.current.has(target.key)) {
      imageCache.current.delete(target.key);
      imageCache.current.set(target.key, image);
    }

    setReady(true);
  }, []);

  const findNearestCachedFrame = useCallback((sequence: number, frame: number, direction: number) => {
    for (let distance = 0; distance < FRAME_COUNT; distance += 1) {
      const candidates = distance === 0
        ? [frame]
        : direction >= 0
          ? [frame - distance, frame + distance]
          : [frame + distance, frame - distance];

      for (const candidate of candidates) {
        if (candidate < 0 || candidate >= FRAME_COUNT) continue;
        const key = `${sequence}:${candidate}`;
        const image = imageCache.current.get(key);

        if (image?.complete && image.naturalWidth) {
          return { target: { sequence, frame: candidate, key }, image };
        }
      }
    }

    return undefined;
  }, []);

  const loadCriticalFrame = useCallback(function runCriticalLoad(target: FrameTarget) {
    const cached = imageCache.current.get(target.key);
    if (cached?.complete && cached.naturalWidth) {
      if (latestFrame.current.key === target.key) displayFrame(target, cached);
      return;
    }

    const wasPending = promiseCache.current.has(target.key);
    if (!wasPending && activeCriticalLoads.current >= MAX_CRITICAL_LOADS) {
      deferredFrame.current = target;
      return;
    }

    if (!wasPending) activeCriticalLoads.current += 1;

    void ensureFrame(target.sequence, target.frame)
      .then((image) => {
        if (latestFrame.current.key === target.key) displayFrame(target, image);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!wasPending) activeCriticalLoads.current = Math.max(0, activeCriticalLoads.current - 1);

        const deferred = deferredFrame.current;
        if (deferred && activeCriticalLoads.current < MAX_CRITICAL_LOADS) {
          deferredFrame.current = undefined;
          runCriticalLoad(deferred);
        }
      });
  }, [displayFrame, ensureFrame]);

  const pumpPreloads = useCallback(function runPreloads() {
    while (activePreloads.current < MAX_PRELOAD_LOADS && preloadQueue.current.length) {
      const target = preloadQueue.current.shift();
      if (!target) break;
      queuedPreloads.current.delete(target.key);

      if (imageCache.current.has(target.key) || promiseCache.current.has(target.key)) continue;

      activePreloads.current += 1;
      void ensureFrame(target.sequence, target.frame)
        .catch(() => undefined)
        .finally(() => {
          activePreloads.current = Math.max(0, activePreloads.current - 1);
          runPreloads();
        });
    }
  }, [ensureFrame]);

  const queuePreload = useCallback((sequence: number, frame: number, priority = false) => {
    const boundedFrame = Math.max(0, Math.min(FRAME_COUNT - 1, frame));
    const key = `${sequence}:${boundedFrame}`;

    if (
      imageCache.current.has(key)
      || promiseCache.current.has(key)
      || queuedPreloads.current.has(key)
    ) return;

    if (!priority && preloadQueue.current.length >= MAX_PRELOAD_QUEUE) return;

    const target = { sequence, frame: boundedFrame, key };
    if (priority) preloadQueue.current.unshift(target);
    else preloadQueue.current.push(target);
    queuedPreloads.current.add(key);

    if (preloadQueue.current.length > MAX_PRELOAD_QUEUE) {
      const removed = preloadQueue.current.pop();
      if (removed) queuedPreloads.current.delete(removed.key);
    }

    pumpPreloads();
  }, [pumpPreloads]);

  const requestFrame = useCallback(
    (sequence: number, frame: number) => {
      const key = `${sequence}:${frame}`;
      const previous = latestFrame.current;
      const direction = sequence > previous.sequence || (sequence === previous.sequence && frame >= previous.frame) ? 1 : -1;

      if (sequence !== previous.sequence) {
        preloadQueue.current = preloadQueue.current.filter((target) => (
          target.sequence >= sequence && target.sequence <= sequence + 1
        ));
        queuedPreloads.current = new Set(preloadQueue.current.map((target) => target.key));
      }

      latestFrame.current = { sequence, frame, key };

      const nearest = findNearestCachedFrame(sequence, frame, direction);
      if (nearest) displayFrame(nearest.target, nearest.image);
      if (nearest?.target.key !== key) loadCriticalFrame({ sequence, frame, key });

      const nearbyOffsets = direction >= 0 ? [-2, -1, 4, 3, 2, 1] : [2, 1, -4, -3, -2, -1];
      for (const offset of nearbyOffsets) {
        queuePreload(sequence, frame + offset, true);
      }

      if (frame > FRAME_COUNT * 0.34 && sequence < CHAPTERS.length - 1) {
        for (let anchor = 0; anchor < FRAME_COUNT; anchor += ANCHOR_INTERVAL) {
          queuePreload(sequence + 1, anchor);
        }
        queuePreload(sequence + 1, FRAME_COUNT - 1);
      }

      if (frame > FRAME_COUNT * 0.7 && sequence < CHAPTERS.length - 1) {
        for (let first = 0; first <= 20; first += 2) {
          queuePreload(sequence + 1, first, true);
        }
      }
    },
    [displayFrame, findNearestCachedFrame, loadCriticalFrame, queuePreload],
  );

  useEffect(() => {
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updateMotion = () => setReducedMotion(motionQuery.matches);
    updateMotion();
    motionQuery.addEventListener("change", updateMotion);

    void ensureFrame(0, 0).then((image) => displayFrame({ sequence: 0, frame: 0, key: "0:0" }, image));

    for (let sequence = 1; sequence < CHAPTERS.length; sequence += 1) {
      queuePreload(sequence, 0);
    }
    for (let anchor = ANCHOR_INTERVAL; anchor < FRAME_COUNT; anchor += ANCHOR_INTERVAL) {
      queuePreload(0, anchor);
    }

    return () => motionQuery.removeEventListener("change", updateMotion);
  }, [displayFrame, ensureFrame, queuePreload]);

  useEffect(() => () => {
    preloadQueue.current = [];
    queuedPreloads.current.clear();

    for (const image of imageCache.current.values()) {
      image.onload = null;
      image.onerror = null;
      image.src = "";
    }
    imageCache.current.clear();
  }, []);

  useEffect(() => {
    const renderFromScroll = () => {
      animationFrame.current = undefined;
      const section = sequenceRef.current;
      if (!section) return;

      const bounds = section.getBoundingClientRect();
      const available = Math.max(1, bounds.height - window.innerHeight);
      const progress = clamp(-bounds.top / available);
      const chapterPosition = progress * CHAPTERS.length;
      const chapter = Math.min(CHAPTERS.length - 1, Math.floor(chapterPosition));
      const localProgress = chapter === CHAPTERS.length - 1 && progress === 1
        ? 1
        : clamp(chapterPosition - chapter);
      const frame = reducedMotion ? Math.round((FRAME_COUNT - 1) * 0.48) : Math.round(localProgress * (FRAME_COUNT - 1));

      setActiveChapter((current) => (current === chapter ? current : chapter));
      if (progressRef.current) progressRef.current.style.transform = `scaleX(${progress})`;
      requestFrame(chapter, frame);
    };

    const scheduleRender = () => {
      if (animationFrame.current !== undefined) return;
      animationFrame.current = window.requestAnimationFrame(renderFromScroll);
    };

    renderFromScroll();
    window.addEventListener("scroll", scheduleRender, { passive: true });
    window.addEventListener("resize", scheduleRender);

    return () => {
      window.removeEventListener("scroll", scheduleRender);
      window.removeEventListener("resize", scheduleRender);
      if (animationFrame.current !== undefined) window.cancelAnimationFrame(animationFrame.current);
    };
  }, [reducedMotion, requestFrame]);

  return (
    <div className="landing-page">
      <header className="landing-header">
        <Link className="landing-brand" to="/" aria-label="DRISHTI landing page">
          <span className="landing-brand-mark" aria-hidden="true">D</span>
          <span>
            <strong>DRISHTI</strong>
            <small>Decision intelligence for public safety</small>
          </span>
        </Link>
        <Link className="landing-enter landing-enter--compact" to="/command">
          Enter platform <ArrowRight aria-hidden="true" />
        </Link>
      </header>

      <main>
        <section
          ref={sequenceRef}
          className="landing-sequence"
          style={{ height: `${100 + CHAPTERS.length * CHAPTER_HEIGHT_VH}vh` }}
          aria-label="DRISHTI platform story"
        >
          <div className="landing-stage">
            <canvas ref={canvasRef} className={ready ? "landing-canvas is-ready" : "landing-canvas"} aria-hidden="true" />
            <div className="landing-vignette" aria-hidden="true" />
            <div className="landing-grid" aria-hidden="true" />

            <div className={ready ? "landing-loader is-hidden" : "landing-loader"} role="status">
              <span />
              Preparing visual sequence
            </div>

            <div className="landing-chapter-rail" aria-label={`Chapter ${activeChapter + 1} of ${CHAPTERS.length}`}>
              {CHAPTERS.map((chapter, index) => (
                <span key={chapter.step} className={index === activeChapter ? "is-active" : ""} />
              ))}
            </div>

            {activeChapter === 0 && (
              <div className="landing-scroll-cue" aria-hidden="true">
                <ChevronDown />
                Scroll to explore
              </div>
            )}

            <div className="landing-copy-layer">
              {CHAPTERS.map((chapter, index) => (
                <section
                  key={chapter.step}
                  className={`landing-chapter landing-chapter--${chapter.align} ${index === activeChapter ? "is-active" : ""}`}
                  aria-label={chapter.step}
                  aria-hidden={index !== activeChapter}
                >
                  <div className="landing-chapter-copy">
                    <p>{chapter.step}</p>
                    <h1>{chapter.title}</h1>
                    <span>{chapter.copy}</span>
                    {index === CHAPTERS.length - 1 && (
                      <Link className="landing-enter" to="/command">
                        Open command center <ArrowRight aria-hidden="true" />
                      </Link>
                    )}
                  </div>
                </section>
              ))}
            </div>

            <div className="landing-progress" aria-hidden="true">
              <div ref={progressRef} />
            </div>
          </div>
        </section>

        <section className="landing-handoff">
          <div>
            <p className="landing-kicker"><ShieldCheck aria-hidden="true" /> Evidence-backed. Human-controlled. Auditable.</p>
            <h2>A common operating picture, from first signal to reviewed action.</h2>
            <p>
              Explore cases, networks, hotspots, forecasts and response workflows inside a platform designed to keep people accountable for every decision.
            </p>
          </div>
          <Link className="landing-enter landing-enter--light" to="/command">
            Enter DRISHTI <ArrowRight aria-hidden="true" />
          </Link>
        </section>
      </main>
    </div>
  );
}
