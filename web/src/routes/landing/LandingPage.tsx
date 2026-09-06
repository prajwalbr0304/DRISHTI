/** DRISHTI — public landing page (route "/").
 *
 * Composition follows the public-safety category convention: a cinematic
 * positioning hero, one full-bleed statement panel per capability, then real
 * product screens as proof and governance as the closing argument. Films are
 * decorative; every claim is carried by text.
 *
 * Load-bearing details: authentication entry points, the page-level motion
 * switch (WCAG 2.2.2 — the films loop indefinitely), lazy film loading, and the
 * synthetic-data disclosure, which appears in the utility strip, the product
 * section and the footer.
 */

import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Check,
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
  BRAND,
  DISCLOSURE,
  FILMS,
  FINAL_CTA,
  FOOTER_COLUMNS,
  GOVERNANCE,
  HERO,
  MISSION,
  MISSION_META,
  NAV_LINKS,
  PILLARS,
  PLATFORM,
  PRINCIPLES,
  PRODUCT_SECTION,
  PRODUCT_SHOTS,
  SHOWCASES,
  SHOWCASE_SECTION,
  STATS,
  STATS_SECTION,
  UTILITY_STRIP,
  type FilmSource,
  type MetaFact,
  type Showcase,
} from "@/routes/landing/landing.data";
import {
  useFilm,
  useMotionSwitch,
  useNearViewport,
  useOverlay,
  useReveal,
  useScrolled,
  type MotionSwitch,
} from "@/routes/landing/landing.hooks";
import "@/routes/landing/landing.css";

function revealDelay(index: number): string | undefined {
  return index <= 0 ? undefined : String(Math.min(index, 4));
}

/* --------------------------------------------------------------------------
   Background film
   ----------------------------------------------------------------------- */

/** A full-bleed looping film with its scrim stack.
 *
 * The `<video>` renders immediately so its poster paints on first frame, but
 * `src` is withheld until the panel is near the viewport. Playback follows the
 * page motion switch rather than the element's own autoplay.
 */
function FilmBackdrop({
  film,
  motion,
  eager = false,
  tone = "panel",
}: {
  film: FilmSource;
  motion: MotionSwitch;
  /** Hero only: load on mount instead of waiting for proximity. */
  eager?: boolean;
  tone?: "hero" | "panel" | "close";
}) {
  const [holderRef, near] = useNearViewport<HTMLDivElement>();
  const armed = eager || near;
  const video = useFilm(film.still, armed, motion.on);

  return (
    <div className={`lp-backdrop lp-backdrop--${tone}`} ref={holderRef} aria-hidden="true">
      <video
        ref={video.ref}
        className={video.ready ? "lp-backdrop-film is-ready" : "lp-backdrop-film"}
        src={armed ? film.src : undefined}
        poster={film.poster}
        muted
        loop
        playsInline
        preload={eager ? "auto" : "none"}
        tabIndex={-1}
        onCanPlay={video.onCanPlay}
        onPlay={video.onPlay}
        onPause={video.onPause}
      />
      <div className="lp-backdrop-shade" />
      <div className="lp-backdrop-grain" />
    </div>
  );
}

/** The page's single motion control. One switch stops every film at once, which
 *  keeps six pause buttons off the design while still satisfying WCAG 2.2.2. */
function MotionToggle({ motion, variant = "bar" }: { motion: MotionSwitch; variant?: "bar" | "cue" }) {
  return (
    <button
      className={variant === "cue" ? "lp-motion lp-motion--cue" : "lp-motion"}
      type="button"
      onClick={motion.toggle}
      aria-pressed={!motion.on}
    >
      <span className="lp-motion-icon" aria-hidden="true">
        {motion.on ? <Pause /> : <Play />}
      </span>
      <span>{motion.on ? "Pause motion" : "Play motion"}</span>
    </button>
  );
}

function MetaList({ items }: { items: readonly MetaFact[] }) {
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

function Brand({ simple = false }: { simple?: boolean }) {
  return (
    <Link className="lp-brand" to="/" aria-label={`${BRAND.name} home`}>
      <span className="lp-brand-mark" aria-hidden="true">
        <span />
      </span>
      <span className="lp-brand-text">
        <strong>{BRAND.name}</strong>
        {!simple && <small>{BRAND.owner}</small>}
      </span>
    </Link>
  );
}

/* --------------------------------------------------------------------------
   Header and mobile navigation
   ----------------------------------------------------------------------- */

function TopBar({ motion }: { motion: MotionSwitch }) {
  const scrolled = useScrolled(40);
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = useCallback(() => setMenuOpen(false), []);
  useOverlay(menuOpen, closeMenu);

  const barClass = ["lp-topbar", scrolled ? "is-scrolled" : "", menuOpen ? "is-menu-open" : ""]
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
            <span className="lp-utility-right">
              <MotionToggle motion={motion} />
              <em>{UTILITY_STRIP.right}</em>
            </span>
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
              <Link className="lp-btn lp-btn--light lp-btn--sm" to="/login">
                Enter platform
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
            <p className="lp-menu-label">Navigate {BRAND.name}</p>
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
              <Link className="lp-btn lp-btn--light" to="/login" onClick={closeMenu}>
                {HERO.primaryCta}
              </Link>
              <MotionToggle motion={motion} />
              <p>{DISCLOSURE.badge}</p>
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

function Hero({ motion }: { motion: MotionSwitch }) {
  return (
    <section className="lp-hero" aria-labelledby="lp-hero-title">
      <FilmBackdrop film={FILMS.vision} motion={motion} tone="hero" eager />

      <div className="lp-shell lp-hero-inner">
        <div className="lp-hero-copy">
          <h1 id="lp-hero-title" data-reveal>
            {HERO.headline}
          </h1>
          <p className="lp-hero-standfirst" data-reveal data-reveal-delay="1">
            {HERO.standfirst}
          </p>
          <div className="lp-cta-row" data-reveal data-reveal-delay="2">
            <Link className="lp-btn lp-btn--light" to="/login">
              {HERO.primaryCta}
            </Link>
            <a className="lp-btn lp-btn--ghost" href={HERO.secondaryHref}>
              {HERO.secondaryCta}
            </a>
          </div>
        </div>
      </div>

      <div className="lp-shell lp-hero-foot">
        <a className="lp-scroll-cue" href="#platform">
          <ArrowDown aria-hidden="true" />
          {HERO.scrollCue}
        </a>
        <MotionToggle motion={motion} variant="cue" />
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------------
   Capability spine
   ----------------------------------------------------------------------- */

function PillarBand() {
  return (
    <section className="lp-pillars" aria-label={`How ${BRAND.name} supports a decision`}>
      <div className="lp-shell lp-pillars-track">
        {PILLARS.map((pillar, index) => (
          <article key={pillar.name} data-reveal data-reveal-delay={revealDelay(index)}>
            <span className="lp-pillar-index">{pillar.index}</span>
            <h2>{pillar.name}</h2>
            <p>{pillar.copy}</p>
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
   Capability showcase — full-bleed statement panels
   ----------------------------------------------------------------------- */

function ShowcasePanel({ panel, motion }: { panel: Showcase; motion: MotionSwitch }) {
  const titleId = `lp-showcase-${panel.id}`;

  return (
    <section
      className={`lp-showcase is-${panel.align}`}
      id={panel.id}
      aria-labelledby={titleId}
    >
      <FilmBackdrop film={panel.film} motion={motion} />

      <div className="lp-shell lp-showcase-inner">
        <div className="lp-showcase-copy">
          <p className="lp-kicker" data-reveal>
            {panel.kicker}
          </p>
          <h2 id={titleId} data-reveal data-reveal-delay="1">
            {panel.headline}
          </h2>
          <p data-reveal data-reveal-delay="2">
            {panel.copy}
          </p>
          <Link className="lp-btn lp-btn--ghost" to="/login" data-reveal data-reveal-delay="3">
            {panel.cta}
          </Link>
        </div>
        <p className="lp-showcase-note" data-reveal data-reveal-delay="3">
          {panel.note}
        </p>
      </div>
    </section>
  );
}

function ShowcaseBand({ motion }: { motion: MotionSwitch }) {
  return (
    <div id="capabilities">
      <section className="lp-showcase-intro" aria-labelledby="lp-showcase-title">
        <div className="lp-shell lp-showcase-intro-inner">
          <div>
            <p className="lp-eyebrow lp-eyebrow--light" data-reveal>
              {SHOWCASE_SECTION.eyebrow}
            </p>
            <h2 id="lp-showcase-title" data-reveal data-reveal-delay="1">
              {SHOWCASE_SECTION.headline}
            </h2>
          </div>
          <p data-reveal data-reveal-delay="2">
            {SHOWCASE_SECTION.standfirst}
          </p>
        </div>
      </section>

      {SHOWCASES.map((panel) => (
        <ShowcasePanel key={panel.id} panel={panel} motion={motion} />
      ))}
    </div>
  );
}

/* --------------------------------------------------------------------------
   Product proof
   ----------------------------------------------------------------------- */

function ProductBand() {
  return (
    <section className="lp-product" id="product" aria-labelledby="lp-product-title">
      <div className="lp-shell">
        <div className="lp-product-head">
          <div>
            <p className="lp-eyebrow" data-reveal>
              {PRODUCT_SECTION.eyebrow}
            </p>
            <h2 id="lp-product-title" data-reveal data-reveal-delay="1">
              {PRODUCT_SECTION.headline}
            </h2>
          </div>
          <div data-reveal data-reveal-delay="2">
            <p>{PRODUCT_SECTION.standfirst}</p>
            <Link className="lp-btn lp-btn--dark lp-btn--sm" to="/login">
              {PRODUCT_SECTION.cta}
            </Link>
          </div>
        </div>

        <div className="lp-product-grid">
          {PRODUCT_SHOTS.map((shot, index) => (
            <Link
              key={shot.id}
              className={shot.feature ? "lp-shot is-feature" : "lp-shot"}
              to="/login"
              aria-labelledby={`lp-shot-${shot.id}`}
              data-reveal
              data-reveal-delay={revealDelay(index % 3)}
            >
              <span className="lp-shot-media">
                <img
                  src={shot.image}
                  alt={shot.alt}
                  loading={shot.feature ? "eager" : "lazy"}
                  decoding="async"
                  width={1280}
                  height={720}
                />
              </span>
              <span className="lp-shot-copy">
                <strong id={`lp-shot-${shot.id}`}>{shot.title}</strong>
                <span>{shot.copy}</span>
                <span className="lp-text-link">
                  Open workspace
                  <ArrowUpRight aria-hidden="true" />
                </span>
              </span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------------
   Audience and scale
   ----------------------------------------------------------------------- */

function AudienceBand() {
  return (
    <section className="lp-audience" id="audience" aria-labelledby="lp-audience-title">
      <div className="lp-shell lp-audience-inner">
        <div className="lp-audience-head">
          <div>
            <p className="lp-eyebrow lp-eyebrow--light" data-reveal>
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

function ScaleBand() {
  return (
    <section className="lp-scale" id="scale" aria-labelledby="lp-scale-title">
      <div className="lp-shell lp-scale-inner">
        <div className="lp-scale-head">
          <p className="lp-eyebrow lp-eyebrow--light" data-reveal>
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
   Mission close
   ----------------------------------------------------------------------- */

function MissionBand({ motion }: { motion: MotionSwitch }) {
  return (
    <section className="lp-mission" id="mission" aria-labelledby="lp-mission-title">
      <FilmBackdrop film={FILMS.ksp} motion={motion} tone="close" />

      <div className="lp-shell lp-mission-inner">
        <p className="lp-eyebrow lp-eyebrow--light" data-reveal>
          {MISSION.eyebrow}
        </p>
        <h2 id="lp-mission-title" data-reveal data-reveal-delay="1">
          {MISSION.headline}
        </h2>
        <p className="lp-mission-body" data-reveal data-reveal-delay="2">
          {MISSION.body}
        </p>

        <div className="lp-mission-foot" data-reveal data-reveal-delay="3">
          <MetaList items={MISSION_META} />
          <span className="lp-mission-strip">{MISSION.strip}</span>
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
          <Link className="lp-btn lp-btn--light" to="/login">
            {FINAL_CTA.cta}
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
          <span>© {new Date().getFullYear()} {BRAND.name} prototype</span>
          <span>{DISCLOSURE.stack}</span>
          <span>{BRAND.owner}</span>
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
  const motion = useMotionSwitch();

  return (
    <div className={motion.on ? "landing" : "landing is-still"} ref={pageRef}>
      <a className="lp-skip-link" href="#main-content">
        Skip to main content
      </a>
      <TopBar motion={motion} />

      <main id="main-content">
        <Hero motion={motion} />
        <PillarBand />
        <PlatformBand />
        <ShowcaseBand motion={motion} />
        <ProductBand />
        <AudienceBand />
        <ScaleBand />
        <GovernanceBand />
        <MissionBand motion={motion} />
        <FinalCta />
      </main>

      <LandingFooter />
    </div>
  );
}
