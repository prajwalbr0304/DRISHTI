import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowDown,
  ArrowRight,
  Database,
  MapPinned,
  Network,
  Pause,
  Play,
  Radar,
  ShieldCheck,
} from "lucide-react";
import "@/routes/landing/landing.css";

const HERO_VIDEO = "/landing/drishti-hero.mp4";
const HERO_POSTER = "/landing/drishti-hero-poster.webp";

const CAPABILITIES = [
  {
    index: "01",
    icon: Database,
    title: "Unify the operational picture",
    copy: "Bring cases, evidence, entities and jurisdiction context into one governed view without losing the source behind the record.",
  },
  {
    index: "02",
    icon: Network,
    title: "Connect what matters",
    copy: "Move from an isolated event to explainable relationships, timelines and leads while keeping every conclusion open to human review.",
  },
  {
    index: "03",
    icon: Radar,
    title: "See change before it becomes noise",
    copy: "Surface emerging patterns and operational pressure with confidence, provenance and clear limits on what the analysis can claim.",
  },
] as const;

export function LandingPage() {
  const heroVideoRef = useRef<HTMLVideoElement>(null);
  const [videoReady, setVideoReady] = useState(false);
  const [videoPlaying, setVideoPlaying] = useState(true);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");

    const applyMotionPreference = () => {
      const video = heroVideoRef.current;
      if (!video) return;

      if (query.matches) {
        video.pause();
        video.currentTime = Math.min(9, video.duration || 9);
        setVideoPlaying(false);
      } else {
        void video.play().then(() => setVideoPlaying(true)).catch(() => setVideoPlaying(false));
      }
    };

    applyMotionPreference();
    query.addEventListener("change", applyMotionPreference);
    return () => query.removeEventListener("change", applyMotionPreference);
  }, []);

  const toggleHeroVideo = () => {
    const video = heroVideoRef.current;
    if (!video) return;

    if (video.paused) {
      void video.play().then(() => setVideoPlaying(true)).catch(() => setVideoPlaying(false));
    } else {
      video.pause();
      setVideoPlaying(false);
    }
  };

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

        <nav className="landing-nav" aria-label="Landing page navigation">
          <a href="#platform">Platform</a>
          <a href="#capabilities">Capabilities</a>
          <a href="#principles">Principles</a>
        </nav>

        <Link className="landing-enter landing-enter--compact" to="/login">
          Enter platform <ArrowRight aria-hidden="true" />
        </Link>
      </header>

      <main>
        <section className="landing-hero" aria-labelledby="landing-hero-title">
          <video
            ref={heroVideoRef}
            className={videoReady ? "landing-hero-film is-ready" : "landing-hero-film"}
            autoPlay
            muted
            loop
            playsInline
            preload="auto"
            poster={HERO_POSTER}
            onCanPlay={() => setVideoReady(true)}
            onPlay={() => setVideoPlaying(true)}
            onPause={() => setVideoPlaying(false)}
          >
            <source src={HERO_VIDEO} type="video/mp4" />
          </video>

          <div className="landing-hero-scrim" aria-hidden="true" />
          <div className="landing-grid" aria-hidden="true" />
          <div className="landing-film-noise" aria-hidden="true" />

          <div className={videoReady ? "landing-loader is-hidden" : "landing-loader"} role="status">
            <span />
            Establishing operational picture
          </div>

          <div className="landing-hero-content">
            <div className="landing-hero-intro">
              <p>You are now entering</p>
              <span>Evidence-backed intelligence</span>
              <span>Human-controlled decisions</span>
            </div>

            <div className="landing-hero-meta" aria-label="Platform context">
              <div>
                <span>Area of operations</span>
                <strong>Karnataka, India</strong>
              </div>
              <div>
                <span>Operational posture</span>
                <strong>Observe · Understand · Respond</strong>
              </div>
              <div>
                <span>Demonstration</span>
                <strong>Synthetic geospatial events</strong>
              </div>
            </div>

            <h1 id="landing-hero-title">DRISHTI</h1>

            <div className="landing-hero-footer">
              <p>One governed operating picture for cases, patterns, jurisdictions and coordinated response.</p>
              <Link className="landing-enter landing-enter--hero" to="/login">
                Open command center <ArrowRight aria-hidden="true" />
              </Link>
            </div>
          </div>

          <button
            className="landing-film-control"
            type="button"
            onClick={toggleHeroVideo}
            aria-label={videoPlaying ? "Pause hero film" : "Play hero film"}
          >
            {videoPlaying ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
            <span>{videoPlaying ? "Pause film" : "Play film"}</span>
          </button>

          <a className="landing-scroll-cue" href="#platform">
            <span>Scroll to explore</span>
            <ArrowDown aria-hidden="true" />
          </a>
        </section>

        <section className="landing-manifesto" id="platform">
          <div className="landing-section-index" aria-hidden="true">
            <span>[ A ]</span>
            <span>THE PLATFORM</span>
          </div>
          <div className="landing-manifesto-copy">
            <p className="landing-kicker">A shared operational language</p>
            <h2>From statewide signal to reviewed action.</h2>
            <p>
              DRISHTI connects geospatial context, investigative records, evidence and analytical models
              so teams can move from an emerging event to an accountable response without surrendering
              judgement to automation.
            </p>
          </div>
          <div className="landing-manifesto-aside">
            <MapPinned aria-hidden="true" />
            <span>Built around Karnataka’s operational context</span>
            <small>Every analytical output retains its source, confidence and review status.</small>
          </div>
        </section>

        <section className="landing-film-chapter" aria-labelledby="second-film-title">
          <div className="landing-film-chapter-copy">
            <p className="landing-kicker">02 / Product film</p>
            <h2 id="second-film-title">The next operational story lives here.</h2>
            <p>
              This full-bleed stage is prepared for the next DRISHTI film. It keeps the same cinematic
              proportions, overlay system and responsive behavior as the opening experience.
            </p>
          </div>

          {/*
            SECOND FILM SLOT
            Replace this reserved-media block with:
            <video autoPlay muted loop playsInline poster="/landing/your-poster.webp">
              <source src="/landing/drishti-capability-02.mp4" type="video/mp4" />
            </video>
          */}
          <div className="landing-reserved-media" aria-label="Reserved stage for a future DRISHTI product film">
            <div className="landing-reserved-grid" aria-hidden="true" />
            <div className="landing-reserved-orbit landing-reserved-orbit--one" aria-hidden="true" />
            <div className="landing-reserved-orbit landing-reserved-orbit--two" aria-hidden="true" />
            <div className="landing-reserved-core" aria-hidden="true">
              <MapPinned />
            </div>
            <div className="landing-reserved-label">
              <span>FILM MODULE 02</span>
              <strong>Reserved for the next visual sequence</strong>
            </div>
            <div className="landing-reserved-status">
              <i />
              Stage prepared
            </div>
          </div>
        </section>

        <section className="landing-capabilities" id="capabilities">
          <div className="landing-section-index" aria-hidden="true">
            <span>[ B ]</span>
            <span>CORE CAPABILITIES</span>
          </div>

          <div className="landing-capabilities-heading">
            <p className="landing-kicker">The operating system for accountable decisions</p>
            <h2>See the whole picture. Keep every decision explainable.</h2>
          </div>

          <div className="landing-capability-list">
            {CAPABILITIES.map((capability) => {
              const Icon = capability.icon;
              return (
                <article key={capability.index} className="landing-capability">
                  <div className="landing-capability-number">{capability.index}</div>
                  <Icon aria-hidden="true" />
                  <h3>{capability.title}</h3>
                  <p>{capability.copy}</p>
                  <span className="landing-capability-line" aria-hidden="true" />
                </article>
              );
            })}
          </div>
        </section>

        <section className="landing-principles" id="principles">
          <div className="landing-principles-visual" aria-hidden="true">
            <div className="landing-principles-ring" />
            <div className="landing-principles-pulse" />
            <span>HUMAN</span>
            <small>IN CONTROL</small>
          </div>
          <div className="landing-principles-copy">
            <p className="landing-kicker"><ShieldCheck aria-hidden="true" /> Governed by design</p>
            <h2>Software informs. People decide.</h2>
            <p>
              Predictions are labelled, uncertainty remains visible and sensitive records stay within
              role and jurisdiction boundaries. DRISHTI is designed to strengthen professional judgement,
              not replace it.
            </p>
            <ul>
              <li><span>01</span> Source-aware analytical outputs</li>
              <li><span>02</span> Role and jurisdiction controls</li>
              <li><span>03</span> Human review before operational action</li>
              <li><span>04</span> Complete audit and provenance trail</li>
            </ul>
          </div>
        </section>

        <section className="landing-final-cta">
          <p className="landing-kicker">Ready for the common operating picture?</p>
          <h2>Turn fragmented signals into coordinated understanding.</h2>
          <Link className="landing-enter landing-enter--final" to="/login">
            Enter DRISHTI <ArrowRight aria-hidden="true" />
          </Link>
        </section>
      </main>

      <footer className="landing-footer">
        <Link className="landing-brand" to="/" aria-label="DRISHTI home">
          <span className="landing-brand-mark" aria-hidden="true">D</span>
          <span><strong>DRISHTI</strong></span>
        </Link>
        <p>Decision intelligence for public safety.</p>
        <span>Evidence-backed · Human-controlled · Auditable</span>
      </footer>
    </div>
  );
}
