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
const INCIDENT_VIDEO = "/landing/drishti-capability-02.mp4";
const INCIDENT_POSTER = "/landing/drishti-capability-02-poster.webp";
const CLOSING_VIDEO = "/landing/drishti-closing-film.mp4";
const CLOSING_POSTER = "/landing/drishti-closing-poster.webp";

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

const OPERATING_SEQUENCE = [
  {
    index: "01",
    title: "Detect",
    copy: "A location-aware incident enters the operational picture.",
  },
  {
    index: "02",
    title: "Connect",
    copy: "People, cases, evidence and geography resolve into one graph.",
  },
  {
    index: "03",
    title: "Explain",
    copy: "Models surface patterns with provenance, confidence and limits.",
  },
  {
    index: "04",
    title: "Review",
    copy: "An authorised officer decides the next operational action.",
  },
] as const;

const PLATFORM_FACTS = [
  { value: "100,003", label: "case records indexed" },
  { value: "206,026", label: "governed graph records" },
  { value: "32", label: "districts represented" },
  { value: "100%", label: "human-reviewed actions" },
] as const;

export function LandingPage() {
  const heroVideoRef = useRef<HTMLVideoElement>(null);
  const incidentVideoRef = useRef<HTMLVideoElement>(null);
  const closingVideoRef = useRef<HTMLVideoElement>(null);
  const [videoReady, setVideoReady] = useState(false);
  const [videoPlaying, setVideoPlaying] = useState(true);
  const [incidentReady, setIncidentReady] = useState(false);
  const [incidentPlaying, setIncidentPlaying] = useState(true);
  const [closingReady, setClosingReady] = useState(false);
  const [closingPlaying, setClosingPlaying] = useState(true);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");

    const applyMotionPreference = () => {
      const videos = [
        { element: heroVideoRef.current, setPlaying: setVideoPlaying, stillFrame: 9 },
        { element: incidentVideoRef.current, setPlaying: setIncidentPlaying, stillFrame: 9.2 },
        { element: closingVideoRef.current, setPlaying: setClosingPlaying, stillFrame: 5 },
      ];

      videos.forEach(({ element, setPlaying, stillFrame }) => {
        if (!element) return;

        if (query.matches) {
          element.pause();
          element.currentTime = Math.min(stillFrame, element.duration || stillFrame);
          setPlaying(false);
        } else {
          void element.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
        }
      });
    };

    applyMotionPreference();
    query.addEventListener("change", applyMotionPreference);
    return () => query.removeEventListener("change", applyMotionPreference);
  }, []);

  const toggleVideo = (
    video: HTMLVideoElement | null,
    setPlaying: (playing: boolean) => void,
  ) => {
    if (!video) return;

    if (video.paused) {
      void video.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
    } else {
      video.pause();
      setPlaying(false);
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
          <a href="#workflow">Workflow</a>
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
            onClick={() => toggleVideo(heroVideoRef.current, setVideoPlaying)}
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

        <section className="landing-film-chapter" id="workflow" aria-labelledby="second-film-title">
          <div className="landing-film-chapter-copy">
            <p className="landing-kicker">02 / Signal to decision</p>
            <h2 id="second-film-title">One incident. Every relevant connection.</h2>
            <p>
              A single incident becomes a shared, explainable picture: location, people, related cases,
              evidence and forecast signals are connected before an authorised officer reviews the
              recommended response.
            </p>

            <ol className="landing-operating-sequence" aria-label="DRISHTI operational sequence">
              {OPERATING_SEQUENCE.map((step) => (
                <li key={step.index}>
                  <span>{step.index}</span>
                  <div>
                    <strong>{step.title}</strong>
                    <small>{step.copy}</small>
                  </div>
                </li>
              ))}
            </ol>
          </div>

          <div className="landing-chapter-media">
            <video
              ref={incidentVideoRef}
              className={incidentReady ? "landing-chapter-video is-ready" : "landing-chapter-video"}
              autoPlay
              muted
              loop
              playsInline
              preload="metadata"
              poster={INCIDENT_POSTER}
              aria-label="Animated DRISHTI incident analysis across Karnataka"
              onCanPlay={() => setIncidentReady(true)}
              onPlay={() => setIncidentPlaying(true)}
              onPause={() => setIncidentPlaying(false)}
            >
              <source src={INCIDENT_VIDEO} type="video/mp4" />
            </video>

            <div className="landing-chapter-scrim" aria-hidden="true" />
            <div className="landing-chapter-grid" aria-hidden="true" />
            <div className="landing-film-noise" aria-hidden="true" />

            <div className={incidentReady ? "landing-chapter-loader is-hidden" : "landing-chapter-loader"} role="status">
              <span />
              Resolving incident graph
            </div>

            <div className="landing-chapter-index">
              <span>OPERATIONAL SEQUENCE 02</span>
              <strong>Karnataka incident intelligence</strong>
            </div>

            <dl className="landing-chapter-meta">
              <div>
                <dt>Area</dt>
                <dd>Karnataka</dd>
              </div>
              <div>
                <dt>Signal</dt>
                <dd>Incident detected</dd>
              </div>
              <div>
                <dt>Control</dt>
                <dd>Human review required</dd>
              </div>
            </dl>

            <strong className="landing-chapter-word" aria-hidden="true">CONNECTED</strong>

            <div className="landing-chapter-footer">
              <p>From incident to coordinated understanding.</p>
              <button
                className="landing-chapter-control"
                type="button"
                onClick={() => toggleVideo(incidentVideoRef.current, setIncidentPlaying)}
                aria-label={incidentPlaying ? "Pause incident film" : "Play incident film"}
              >
                {incidentPlaying ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
                <span>{incidentPlaying ? "Pause sequence" : "Play sequence"}</span>
              </button>
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

        <section className="landing-proof" aria-labelledby="landing-proof-title">
          <div>
            <p className="landing-kicker">Operational scale, visible</p>
            <h2 id="landing-proof-title">Built on governed data, not disconnected dashboards.</h2>
          </div>
          <dl>
            {PLATFORM_FACTS.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.value}</dt>
                <dd>{fact.label}</dd>
              </div>
            ))}
          </dl>
          <p className="landing-proof-note">
            Prototype inventory from the DRISHTI operational dataset. Counts communicate system scale;
            the landing experience uses synthetic demonstration data.
          </p>
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

        <section className="landing-closing-film" aria-labelledby="closing-film-title">
          <video
            ref={closingVideoRef}
            className={closingReady ? "landing-closing-video is-ready" : "landing-closing-video"}
            autoPlay
            muted
            loop
            playsInline
            preload="metadata"
            poster={CLOSING_POSTER}
            aria-label="Karnataka Police emblem and statewide intelligence visual"
            onCanPlay={() => setClosingReady(true)}
            onPlay={() => setClosingPlaying(true)}
            onPause={() => setClosingPlaying(false)}
          >
            <source src={CLOSING_VIDEO} type="video/mp4" />
          </video>

          <div className="landing-closing-scrim" aria-hidden="true" />
          <div className="landing-grid" aria-hidden="true" />
          <div className="landing-film-noise" aria-hidden="true" />

          <div className={closingReady ? "landing-closing-loader is-hidden" : "landing-closing-loader"} role="status">
            <span />
            Establishing statewide mission
          </div>

          <div className="landing-closing-content">
            <div className="landing-closing-index">
              <span>03 / Mission</span>
              <strong>Decision intelligence for public safety</strong>
            </div>

            <div className="landing-closing-copy">
              <p className="landing-kicker">Purpose-built for Karnataka</p>
              <h2 id="closing-film-title">Intelligence in service of safer communities.</h2>
              <p>
                A secure operating picture that helps Karnataka Police understand events, coordinate
                across jurisdictions and act with evidence, accountability and human judgement.
              </p>
            </div>

            <dl className="landing-closing-meta">
              <div>
                <dt>Scope</dt>
                <dd>Statewide operations</dd>
              </div>
              <div>
                <dt>Foundation</dt>
                <dd>Governed ontology</dd>
              </div>
              <div>
                <dt>Authority</dt>
                <dd>Human in control</dd>
              </div>
            </dl>

            <div className="landing-closing-footer">
              <span>Observe · Understand · Coordinate · Review</span>
              <button
                className="landing-chapter-control"
                type="button"
                onClick={() => toggleVideo(closingVideoRef.current, setClosingPlaying)}
                aria-label={closingPlaying ? "Pause closing film" : "Play closing film"}
              >
                {closingPlaying ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
                <span>{closingPlaying ? "Pause film" : "Play film"}</span>
              </button>
            </div>
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
