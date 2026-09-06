/** DRISHTI — public landing page (route "/").
 *
 * A mission-led, product-first composition. Cinematic media establishes the
 * operating context; real DRISHTI screens provide the proof. Authentication,
 * reduced-motion behavior, and the synthetic-data disclosure are load-bearing.
 */

import { useCallback, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  MapPinned,
  Menu,
  Pause,
  Play,
  ShieldCheck,
  X,
} from "lucide-react";

import {
  AUDIENCES,
  AUDIENCE_SECTION,
  DISCLOSURE,
  FINAL_CTA,
  FOOTER_COLUMNS,
  GOVERNANCE,
  HERO,
  HERO_FACTS,
  INTELLIGENCE,
  MEDIA,
  MISSION,
  MISSION_META,
  NAV_LINKS,
  PILLARS,
  PLATFORM,
  PRINCIPLES,
  SEQUENCE,
  SEQUENCE_META,
  SPOTLIGHTS,
  SPOTLIGHT_SECTION,
  STATS,
  STATS_SECTION,
  STILL_FRAMES,
  UTILITY_STRIP,
  type HeroFact,
} from "@/routes/landing/landing.data";
import {
  useFilm,
  useOverlay,
  useReveal,
  useScrolled,
  type Film,
} from "@/routes/landing/landing.hooks";
import "@/routes/landing/landing.css";

function revealDelay(index: number): string | undefined {
  return index <= 0 ? undefined : String(Math.min(index, 4));
}

/* --------------------------------------------------------------------------
   Shared pieces
   ----------------------------------------------------------------------- */

function Brand({ simple = false }: { simple?: boolean }) {
  return (
    <Link className="lp-brand" to="/" aria-label="DRISHTI home">
      <span className="lp-brand-mark" aria-hidden="true">
        <span />
      </span>
      <span className="lp-brand-text">
        <strong>DRISHTI</strong>
        {!simple && <small>Decision intelligence</small>}
      </span>
    </Link>
  );
}

function FilmLayers() {
  return (
    <>
      <div className="lp-film-shade" aria-hidden="true" />
      <div className="lp-film-grid" aria-hidden="true" />
      <div className="lp-film-glow" aria-hidden="true" />
    </>
  );
}

function BackgroundFilm({
  film,
  src,
  poster,
  priority = false,
}: {
  film: Film;
  src: string;
  poster: string;
  priority?: boolean;
}) {
  return (
    <video
      ref={film.ref}
      className={film.ready ? "lp-film is-ready" : "lp-film"}
      autoPlay
      muted
      loop
      playsInline
      preload={priority ? "auto" : "metadata"}
      poster={poster}
      aria-hidden="true"
      tabIndex={-1}
      onCanPlay={film.onCanPlay}
      onPlay={film.onPlay}
      onPause={film.onPause}
    >
      <source src={src} type="video/mp4" />
    </video>
  );
}

function FilmControl({ film, label }: { film: Film; label: string }) {
  return (
    <button
      className="lp-film-btn"
      type="button"
      onClick={film.toggle}
      aria-label={film.playing ? `Pause ${label}` : `Play ${label}`}
    >
      <span className="lp-film-btn-icon" aria-hidden="true">
        {film.playing ? <Pause /> : <Play />}
      </span>
      <span>{film.playing ? "Pause film" : "Play film"}</span>
    </button>
  );
}

function FilmLoader({ ready, label }: { ready: boolean; label: string }) {
  return (
    <p className={ready ? "lp-loader is-hidden" : "lp-loader"} aria-hidden="true">
      <span />
      {label}
    </p>
  );
}

function MetaList({ items }: { items: readonly HeroFact[] }) {
  return (
    <dl className="lp-meta">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/* --------------------------------------------------------------------------
   Header and mobile navigation
   ----------------------------------------------------------------------- */

function TopBar() {
  const scrolled = useScrolled(32);
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = useCallback(() => setMenuOpen(false), []);
  useOverlay(menuOpen, closeMenu);

  const barClass = [
    "lp-topbar",
    scrolled ? "is-scrolled" : "",
    menuOpen ? "is-menu-open" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <>
      <div className={barClass}>
        <div className="lp-utility">
          <div className="lp-shell lp-utility-inner">
            <span>
              <ShieldCheck aria-hidden="true" />
              {UTILITY_STRIP.left}
            </span>
            <span>{UTILITY_STRIP.right}</span>
          </div>
        </div>

        <header className="lp-header">
          <div className="lp-shell lp-header-inner">
            <Brand />

            <nav className="lp-nav" aria-label="Page sections">
              {NAV_LINKS.map((link) => (
                <a key={link.href} href={link.href}>
                  {link.label}
                </a>
              ))}
            </nav>

            <div className="lp-header-actions">
              <Link className="lp-header-login" to="/login">
                Sign in
              </Link>
              <Link className="lp-btn lp-btn--primary lp-btn--sm" to="/login">
                Enter platform
                <ArrowUpRight aria-hidden="true" />
              </Link>
              <button
                className="lp-burger"
                type="button"
                aria-expanded={menuOpen}
                aria-controls="lp-mobile-menu"
                aria-label={menuOpen ? "Close menu" : "Open menu"}
                onClick={() => setMenuOpen((open) => !open)}
              >
                {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
              </button>
            </div>
          </div>
        </header>
      </div>

      {menuOpen && (
        <nav className="lp-menu" id="lp-mobile-menu" aria-label="Page sections">
          <div className="lp-shell lp-menu-inner">
            <p className="lp-menu-label">Navigate DRISHTI</p>
            <div className="lp-menu-links">
              {NAV_LINKS.map((link, index) => (
                <a key={link.href} href={link.href} onClick={closeMenu}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  {link.label}
                  <ArrowRight aria-hidden="true" />
                </a>
              ))}
            </div>
            <div className="lp-menu-foot">
              <Link className="lp-btn lp-btn--primary" to="/login" onClick={closeMenu}>
                Enter the platform
                <ArrowUpRight aria-hidden="true" />
              </Link>
              <p>Prototype experience · Synthetic records only</p>
            </div>
          </div>
        </nav>
      )}
    </>
  );
}

/* --------------------------------------------------------------------------
   Hero
   ----------------------------------------------------------------------- */

function Hero({ film }: { film: Film }) {
  return (
    <section className="lp-hero" aria-labelledby="lp-hero-title">
      <BackgroundFilm
        film={film}
        src={MEDIA.heroVideo}
        poster={MEDIA.heroPoster}
        priority
      />
      <FilmLayers />
      <FilmLoader ready={film.ready} label={HERO.loader} />

      <div className="lp-shell lp-hero-inner">
        <div className="lp-hero-copy">
          <p className="lp-eyebrow lp-eyebrow--light" data-reveal>
            {HERO.eyebrow}
          </p>
          <h1 id="lp-hero-title" data-reveal data-reveal-delay="1">
            {HERO.headline.map((line, index) => (
              <span
                className={index === HERO.headline.length - 1 ? "is-accent" : undefined}
                key={line}
              >
                {line}
              </span>
            ))}
          </h1>
          <p className="lp-hero-standfirst" data-reveal data-reveal-delay="2">
            {HERO.standfirst}
          </p>
          <div className="lp-cta-row" data-reveal data-reveal-delay="3">
            <Link className="lp-btn lp-btn--primary" to="/login">
              {HERO.primaryCta}
              <ArrowUpRight aria-hidden="true" />
            </Link>
            <a className="lp-btn lp-btn--glass" href={HERO.secondaryHref}>
              {HERO.secondaryCta}
              <ArrowDown aria-hidden="true" />
            </a>
          </div>
        </div>

        <aside className="lp-hero-card" data-reveal data-reveal-delay="3">
          <div className="lp-hero-card-status">
            <span aria-hidden="true" />
            {HERO.statusLabel}
          </div>
          <h2>{HERO.statusTitle}</h2>
          <dl>
            {HERO_FACTS.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        </aside>

        <div className="lp-hero-foot" data-reveal data-reveal-delay="4">
          <a className="lp-scroll-cue" href="#platform">
            <span>{HERO.scrollCue}</span>
            <ArrowDown aria-hidden="true" />
          </a>
          <div className="lp-hero-foot-line" aria-hidden="true" />
          <FilmControl film={film} label="hero film" />
        </div>
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------------
   Capability spine
   ----------------------------------------------------------------------- */

function PillarBand() {
  return (
    <section className="lp-pillars" aria-label="DRISHTI's decision-intelligence workflow">
      <div className="lp-pillars-track lp-shell">
        {PILLARS.map((pillar, index) => (
          <article key={pillar.name} data-reveal data-reveal-delay={revealDelay(index)}>
            <span className="lp-pillar-index">{pillar.index}</span>
            <div>
              <h2>{pillar.name}</h2>
              <p>{pillar.copy}</p>
            </div>
            <ChevronRight aria-hidden="true" />
          </article>
        ))}
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------------
   Platform statement
   ----------------------------------------------------------------------- */

function PlatformBand() {
  return (
    <section className="lp-platform" id="platform" aria-labelledby="lp-platform-title">
      <div className="lp-shell lp-platform-inner">
        <div className="lp-platform-heading">
          <p className="lp-eyebrow" data-reveal>
            {PLATFORM.eyebrow}
          </p>
          <h2 id="lp-platform-title" data-reveal data-reveal-delay="1">
            {PLATFORM.headline}
          </h2>
        </div>

        <div className="lp-platform-copy">
          {PLATFORM.body.map((paragraph, index) => (
            <p key={paragraph.slice(0, 28)} data-reveal data-reveal-delay={revealDelay(index + 1)}>
              {paragraph}
            </p>
          ))}

          <div className="lp-callout" data-reveal data-reveal-delay="3">
            <span className="lp-callout-icon" aria-hidden="true">
              <MapPinned />
            </span>
            <div>
              <strong>{PLATFORM.callout.label}</strong>
              <p>{PLATFORM.callout.copy}</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------------
   Product proof
   ----------------------------------------------------------------------- */

function ProductWindow({ image, alt }: { image: string; alt: string }) {
  return (
    <div className="lp-product-window">
      <div className="lp-window-bar" aria-hidden="true">
        <span className="lp-window-dots">
          <i />
          <i />
          <i />
        </span>
        <span>secure.drishti / operating-picture</span>
        <span className="lp-window-state">Live prototype</span>
      </div>
      <div className="lp-window-image">
        <img src={image} alt={alt} decoding="async" width={1280} height={720} />
      </div>
    </div>
  );
}

function SpotlightBand() {
  const [lead, ...cards] = SPOTLIGHTS;

  return (
    <section className="lp-products" id="capabilities" aria-labelledby="lp-capabilities-title">
      <div className="lp-shell">
        <div className="lp-products-head">
          <div>
            <p className="lp-eyebrow" data-reveal>
              {SPOTLIGHT_SECTION.eyebrow}
            </p>
            <h2 id="lp-capabilities-title" data-reveal data-reveal-delay="1">
              {SPOTLIGHT_SECTION.headline}
            </h2>
          </div>
          <p data-reveal data-reveal-delay="2">
            {SPOTLIGHT_SECTION.standfirst}
          </p>
        </div>

        <Link
          className="lp-product-lead"
          to="/login"
          aria-labelledby={`lp-card-${lead.id}`}
          data-reveal
        >
          <ProductWindow image={lead.image} alt={lead.alt} />
          <div className="lp-product-lead-copy">
            <div>
              <p className="lp-card-kicker">{lead.eyebrow}</p>
              <h3 id={`lp-card-${lead.id}`}>{lead.title}</h3>
            </div>
            <p>{lead.copy}</p>
            <span className="lp-text-link">
              Open the operating picture
              <ArrowUpRight aria-hidden="true" />
            </span>
          </div>
        </Link>

        <div className="lp-product-grid">
          {cards.map((card, index) => (
            <Link
              key={card.id}
              className={card.wide ? "lp-product-card is-wide" : "lp-product-card"}
              to="/login"
              aria-labelledby={`lp-card-${card.id}`}
              style={{ "--card-span": card.span } as CSSProperties}
              data-reveal
              data-reveal-delay={revealDelay(index % 2)}
            >
              <div className="lp-product-card-media">
                <img
                  src={card.image}
                  alt={card.alt}
                  loading="lazy"
                  decoding="async"
                  width={1280}
                  height={720}
                />
              </div>
              <div className="lp-product-card-copy">
                <p className="lp-card-kicker">{card.eyebrow}</p>
                <h3 id={`lp-card-${card.id}`}>{card.title}</h3>
                <p>{card.copy}</p>
                <span className="lp-text-link">
                  Explore capability
                  <ArrowUpRight aria-hidden="true" />
                </span>
              </div>
            </Link>
          ))}
        </div>

        <div className="lp-module-strip" data-reveal>
          <span>Also in the platform</span>
          <ul>
            {SPOTLIGHT_SECTION.supportingModules.map((module) => (
              <li key={module}>
                <Check aria-hidden="true" />
                {module}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------------
   Connected intelligence
   ----------------------------------------------------------------------- */

function IntelligenceBand({ film }: { film: Film }) {
  return (
    <section
      className="lp-intelligence"
      id="intelligence"
      aria-labelledby="lp-intelligence-title"
    >
      <div className="lp-shell">
        <div className="lp-intelligence-head">
          <p className="lp-eyebrow lp-eyebrow--light" data-reveal>
            {INTELLIGENCE.eyebrow}
          </p>
          <h2 id="lp-intelligence-title" data-reveal data-reveal-delay="1">
            {INTELLIGENCE.headline}
          </h2>
          <p data-reveal data-reveal-delay="2">
            {INTELLIGENCE.body}
          </p>
        </div>

        <div className="lp-intelligence-grid">
          <div className="lp-intelligence-visual" data-reveal>
            <BackgroundFilm
              film={film}
              src={MEDIA.intelligenceVideo}
              poster={MEDIA.intelligencePoster}
            />
            <FilmLayers />
            <FilmLoader ready={film.ready} label={INTELLIGENCE.loader} />

            <div className="lp-visual-head">
              <div>
                <span>{INTELLIGENCE.panelLabel}</span>
                <strong>{INTELLIGENCE.panelTitle}</strong>
              </div>
              <span className="lp-live-chip">
                <i aria-hidden="true" />
                Connected
              </span>
            </div>

            <strong className="lp-visual-word" aria-hidden="true">
              {INTELLIGENCE.word}
            </strong>

            <div className="lp-visual-foot">
              <MetaList items={SEQUENCE_META} />
              <div className="lp-visual-caption">
                <p>{INTELLIGENCE.caption}</p>
                <FilmControl film={film} label="connected intelligence film" />
              </div>
            </div>
          </div>

          <ol className="lp-sequence">
            {SEQUENCE.map((step, index) => (
              <li key={step.index} data-reveal data-reveal-delay={revealDelay(index)}>
                <span className="lp-sequence-index">{step.index}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.copy}</p>
                </div>
                <ArrowRight aria-hidden="true" />
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------------
   Prototype scale
   ----------------------------------------------------------------------- */

function ScaleBand() {
  return (
    <section className="lp-scale" id="scale" aria-labelledby="lp-scale-title">
      <div className="lp-shell lp-scale-inner">
        <div className="lp-scale-head">
          <p className="lp-eyebrow" data-reveal>
            {STATS_SECTION.eyebrow}
          </p>
          <h2 id="lp-scale-title" data-reveal data-reveal-delay="1">
            {STATS_SECTION.headline}
          </h2>
        </div>

        <dl className="lp-stats">
          {STATS.map((stat, index) => (
            <div key={stat.label} data-reveal data-reveal-delay={revealDelay(index)}>
              <dt>{stat.value}</dt>
              <dd>{stat.label}</dd>
            </div>
          ))}
        </dl>

        <p className="lp-note" data-reveal>
          <ShieldCheck aria-hidden="true" />
          {STATS_SECTION.note}
        </p>
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------------
   Governance
   ----------------------------------------------------------------------- */

function GovernanceBand() {
  return (
    <section className="lp-governance" id="governance" aria-labelledby="lp-governance-title">
      <div className="lp-shell lp-governance-inner">
        <div className="lp-governance-lead">
          <p className="lp-eyebrow" data-reveal>
            {GOVERNANCE.eyebrow}
          </p>
          <h2 id="lp-governance-title" data-reveal data-reveal-delay="1">
            {GOVERNANCE.headline}
          </h2>
          <p data-reveal data-reveal-delay="2">
            {GOVERNANCE.body}
          </p>

          <div className="lp-governance-seal" data-reveal data-reveal-delay="3">
            <span aria-hidden="true">
              <ShieldCheck />
            </span>
            <div>
              <strong>{GOVERNANCE.sealTitle}</strong>
              <p>{GOVERNANCE.sealCopy}</p>
            </div>
          </div>
        </div>

        <ol className="lp-principles">
          {PRINCIPLES.map((principle, index) => (
            <li key={principle.index} data-reveal data-reveal-delay={revealDelay(index)}>
              <span className="lp-principle-index">{principle.index}</span>
              <div>
                <h3>{principle.title}</h3>
                <p>{principle.copy}</p>
              </div>
              <Check aria-hidden="true" />
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------------
   Mission
   ----------------------------------------------------------------------- */

function MissionBand({ film }: { film: Film }) {
  return (
    <section className="lp-mission" id="mission" aria-labelledby="lp-mission-title">
      <BackgroundFilm film={film} src={MEDIA.missionVideo} poster={MEDIA.missionPoster} />
      <FilmLayers />
      <FilmLoader ready={film.ready} label={MISSION.loader} />

      <div className="lp-shell lp-mission-inner">
        <div className="lp-mission-top">
          <p className="lp-eyebrow lp-eyebrow--light" data-reveal>
            {MISSION.kicker}
          </p>
          <span>{MISSION.eyebrow}</span>
        </div>

        <div className="lp-mission-copy">
          <p className="lp-mission-mark" data-reveal>
            <strong>{MISSION.bigMark}</strong>
            <span>{MISSION.bigMarkSuffix}</span>
          </p>
          <h2 id="lp-mission-title" data-reveal data-reveal-delay="1">
            {MISSION.headline}
          </h2>
          <p data-reveal data-reveal-delay="2">
            {MISSION.body}
          </p>
        </div>

        <div className="lp-mission-foot" data-reveal data-reveal-delay="3">
          <MetaList items={MISSION_META} />
          <div className="lp-mission-control">
            <span>{MISSION.strip}</span>
            <FilmControl film={film} label="mission film" />
          </div>
        </div>
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------------
   Audience
   ----------------------------------------------------------------------- */

function AudienceBand() {
  return (
    <section className="lp-audience" id="audience" aria-labelledby="lp-audience-title">
      <div className="lp-shell lp-audience-inner">
        <div className="lp-audience-head">
          <div>
            <p className="lp-eyebrow" data-reveal>
              {AUDIENCE_SECTION.eyebrow}
            </p>
            <h2 id="lp-audience-title" data-reveal data-reveal-delay="1">
              {AUDIENCE_SECTION.headline}
            </h2>
          </div>
          <p data-reveal data-reveal-delay="2">
            {AUDIENCE_SECTION.standfirst}
          </p>
        </div>

        <div className="lp-audience-grid">
          {AUDIENCES.map((audience, index) => (
            <article key={audience.tier} data-reveal data-reveal-delay={revealDelay(index)}>
              <span className="lp-audience-index">{String(index + 1).padStart(2, "0")}</span>
              <p className="lp-audience-roles">{audience.roles}</p>
              <h3>{audience.tier}</h3>
              <p>{audience.copy}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------------
   Final CTA and footer
   ----------------------------------------------------------------------- */

function FinalCta() {
  return (
    <section className="lp-final" aria-labelledby="lp-final-title">
      <div className="lp-final-orbit" aria-hidden="true" />
      <div className="lp-shell lp-final-inner">
        <p className="lp-eyebrow lp-eyebrow--light" data-reveal>
          {FINAL_CTA.eyebrow}
        </p>
        <h2 id="lp-final-title" data-reveal data-reveal-delay="1">
          {FINAL_CTA.headline.map((line, index) => (
            <span className={index === 1 ? "is-accent" : undefined} key={line}>
              {line}
            </span>
          ))}
        </h2>
        <div className="lp-final-action" data-reveal data-reveal-delay="2">
          <p>{FINAL_CTA.body}</p>
          <Link className="lp-btn lp-btn--primary" to="/login">
            {FINAL_CTA.cta}
            <ArrowUpRight aria-hidden="true" />
          </Link>
        </div>
      </div>
    </section>
  );
}

function LandingFooter() {
  return (
    <footer className="lp-footer">
      <div className="lp-shell">
        <div className="lp-footer-top">
          <div className="lp-footer-brand">
            <Brand simple />
            <p>{DISCLOSURE.brandLine}</p>
            <span className="lp-footer-badge">
              <ShieldCheck aria-hidden="true" />
              {DISCLOSURE.badge}
            </span>
          </div>

          {FOOTER_COLUMNS.map((column) => (
            <div className="lp-footer-col" key={column.heading}>
              <h3>{column.heading}</h3>
              <ul>
                {column.links.map((link) => (
                  <li key={link.label}>
                    {link.href.startsWith("#") ? (
                      <a href={link.href}>{link.label}</a>
                    ) : (
                      <Link to={link.href}>{link.label}</Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="lp-footer-disclosure">
          <ShieldCheck aria-hidden="true" />
          <p>
            <strong>{DISCLOSURE.synthetic}</strong> {DISCLOSURE.notProduction}
          </p>
        </div>

        <div className="lp-footer-meta">
          <span>© {new Date().getFullYear()} DRISHTI prototype</span>
          <span>{DISCLOSURE.stack}</span>
          <span>Karnataka, India</span>
        </div>
      </div>
    </footer>
  );
}

/* --------------------------------------------------------------------------
   Page
   ----------------------------------------------------------------------- */

export function LandingPage() {
  const pageRef = useReveal<HTMLDivElement>();
  const heroFilm = useFilm(STILL_FRAMES.hero);
  const intelligenceFilm = useFilm(STILL_FRAMES.intelligence);
  const missionFilm = useFilm(STILL_FRAMES.mission);

  return (
    <div className="landing" ref={pageRef}>
      <a className="lp-skip-link" href="#main-content">
        Skip to main content
      </a>
      <TopBar />

      <main id="main-content">
        <Hero film={heroFilm} />
        <PillarBand />
        <PlatformBand />
        <SpotlightBand />
        <IntelligenceBand film={intelligenceFilm} />
        <ScaleBand />
        <GovernanceBand />
        <MissionBand film={missionFilm} />
        <AudienceBand />
        <FinalCta />
      </main>

      <LandingFooter />
    </div>
  );
}
