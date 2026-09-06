/** DRISHTI public landing page — content model.
 *
 * Structure follows the public-safety category convention: a cinematic
 * positioning hero, then one full-bleed statement panel per capability, then
 * real product screens as proof, then governance.
 *
 * Two rules constrain every string in this file. Nothing may imply autonomous
 * enforcement — DRISHTI is decision support and a named officer always acts.
 * And nothing may imply production deployment: the dataset behind this
 * demonstration is entirely synthetic, and the page says so in three places.
 */

/* --------------------------------------------------------------------------
   Films
   --------------------------------------------------------------------------
   Background footage. `still` is the second to freeze on when motion is
   suppressed, chosen to match each film's poster frame so the swap from poster
   to paused video is invisible.

   Films under /landing/films/ are built by scripts/build-landing-films.ps1
   from the archived frame sequences in web/media/landing-sequences/.
   ----------------------------------------------------------------------- */

export interface FilmSource {
  src: string;
  poster: string;
  still: number;
  /** Announced by the pause/play control and the reduced-motion caption. */
  label: string;
}

export const FILMS = {
  vision: {
    src: "/landing/films/vision.mp4",
    poster: "/landing/films/vision-poster.webp",
    still: 2.5,
    label: "opening film",
  },
  command: {
    src: "/landing/films/command.mp4",
    poster: "/landing/films/command-poster.webp",
    still: 3.3,
    label: "command centre film",
  },
  statewide: {
    src: "/landing/films/statewide.mp4",
    poster: "/landing/films/statewide-poster.webp",
    still: 3.3,
    label: "statewide geography film",
  },
  reasoning: {
    src: "/landing/films/reasoning.mp4",
    poster: "/landing/films/reasoning-poster.webp",
    still: 3.3,
    label: "reasoning film",
  },
  hotspots: {
    src: "/landing/films/hotspots.mp4",
    poster: "/landing/films/hotspots-poster.webp",
    still: 3.3,
    label: "forecasting film",
  },
  response: {
    src: "/landing/films/response.mp4",
    poster: "/landing/films/response-poster.webp",
    still: 3.3,
    label: "emergency response film",
  },
  ksp: {
    src: "/landing/films/ksp.mp4",
    poster: "/landing/films/ksp-poster.webp",
    still: 3.3,
    label: "closing film",
  },
  casework: {
    src: "/landing/drishti-capability-02.mp4",
    poster: "/landing/drishti-capability-02-poster.webp",
    still: 9.2,
    label: "case intelligence film",
  },
} as const satisfies Record<string, FilmSource>;

/* --------------------------------------------------------------------------
   Chrome
   ----------------------------------------------------------------------- */

export interface NavLink {
  label: string;
  href: string;
}

export const NAV_LINKS: readonly NavLink[] = [
  { label: "Platform", href: "#platform" },
  { label: "Capabilities", href: "#capabilities" },
  { label: "Product", href: "#product" },
  { label: "Who it serves", href: "#audience" },
  { label: "Governance", href: "#governance" },
] as const;

export const UTILITY_STRIP = {
  left: "Prototype experience · Synthetic demonstration data",
  right: "Karnataka State Police · Karnataka, India",
} as const;

export const BRAND = {
  name: "DRISHTI",
  tagline: "Decision intelligence",
  owner: "Karnataka State Police",
} as const;

/* --------------------------------------------------------------------------
   Hero
   ----------------------------------------------------------------------- */

export const HERO = {
  /** Rendered as separate block lines, so the break is deliberate rather than
   *  whatever the viewport width happens to produce. */
  headline: ["See more clearly.", "Act more accountably."],
  standfirst: "The decision intelligence platform for Karnataka State Police",
  primaryCta: "Enter DRISHTI",
  secondaryCta: "See the platform",
  secondaryHref: "#platform",
  scrollCue: "Scroll to explore",
  loader: "Connecting the operating picture",
} as const;

/* --------------------------------------------------------------------------
   Capability spine
   ----------------------------------------------------------------------- */

export interface Pillar {
  index: string;
  name: string;
  copy: string;
}

export const PILLARS: readonly Pillar[] = [
  {
    index: "01",
    name: "Observe",
    copy: "Statewide posture, live incidents and jurisdiction context in one view.",
  },
  {
    index: "02",
    name: "Understand",
    copy: "People, relationships, evidence and geography resolved together.",
  },
  {
    index: "03",
    name: "Investigate",
    copy: "Follow every lead without losing the chain back to its source.",
  },
  {
    index: "04",
    name: "Decide",
    copy: "Review explainable analysis before an authorised officer acts.",
  },
  {
    index: "05",
    name: "Audit",
    copy: "Every query, model run and decision stays accountable afterwards.",
  },
] as const;

/* --------------------------------------------------------------------------
   Platform statement
   ----------------------------------------------------------------------- */

export const PLATFORM = {
  eyebrow: "One operating picture",
  headline: "Fragmented signals become coordinated understanding.",
  body: [
    "Public-safety information arrives in pieces — station records, evidence stores, jurisdiction boundaries, maps and spreadsheets. The hard part was never collecting more data. It is understanding what matters together, fast enough to act on.",
    "DRISHTI connects those pieces without handing judgement to a machine. Sources stay visible, uncertainty stays stated, and a named officer remains responsible for what happens next.",
  ],
  callout: {
    label: "Built for Karnataka's operational context",
    copy: "Every analytical output carries its source, confidence, scope and review status.",
  },
} as const;

/* --------------------------------------------------------------------------
   Capability showcase — full-bleed statement panels
   ----------------------------------------------------------------------- */

export interface Showcase {
  id: string;
  kicker: string;
  headline: string;
  copy: string;
  cta: string;
  film: FilmSource;
  align: "start" | "end";
  /** Small provenance line pinned opposite the copy column. */
  note: string;
}

export const SHOWCASE_SECTION = {
  eyebrow: "Capabilities",
  headline: "One platform, from first signal to final review.",
  standfirst:
    "Crime intelligence and emergency response share the same governed foundation, so context follows the work instead of disappearing between tools.",
} as const;

export const SHOWCASES: readonly Showcase[] = [
  {
    id: "command",
    kicker: "Command Center",
    headline: "Command the whole state",
    copy: "Live incident posture, district workload and emerging pressure in one governed view — so the next order is given with the full picture rather than a fragment of it.",
    cta: "Explore Command Center",
    film: FILMS.command,
    align: "start",
    note: "Statewide posture · 32 districts",
  },
  {
    id: "geospatial",
    kicker: "Map & Hotspots",
    headline: "Put every signal on the ground",
    copy: "Read patterns across districts and taluks on real Karnataka boundaries, then trace any hotspot straight back to the records that produced it.",
    cta: "Explore the map",
    film: FILMS.statewide,
    align: "end",
    note: "PostGIS boundaries · Traceable to source",
  },
  {
    id: "casework",
    kicker: "Case Intelligence",
    headline: "One case, every thread intact",
    copy: "Timelines, people, property, digital evidence and financial activity assemble into a single reviewable record, with provenance carried on every link.",
    cta: "Explore case intelligence",
    film: FILMS.casework,
    align: "start",
    note: "Evidence chain preserved end to end",
  },
  {
    id: "ask",
    kicker: "Ask DRISHTI",
    headline: "Ask plainly. Inspect the answer",
    copy: "Plain-language questions become scoped, deterministic queries that answer with citations back to governed records — never an uncited conclusion.",
    cta: "Explore Ask DRISHTI",
    film: FILMS.reasoning,
    align: "end",
    note: "Cited answers · Deterministic retrieval",
  },
  {
    id: "forecasting",
    kicker: "Analytics & Forecasting",
    headline: "See where pressure is building",
    copy: "Forecasts arrive with confidence bounds, model version and stated limits attached. Planning support for command — never an automatic verdict on a person or a place.",
    cta: "Explore forecasting",
    film: FILMS.hotspots,
    align: "start",
    note: "Labelled predictions · Stated limits",
  },
  {
    id: "response",
    kicker: "Emergency Response",
    headline: "Coordinate the first sixty minutes",
    copy: "Live incidents, hazard forecasts, available resources and response plans in one workspace built for the hours when coordination decides the outcome.",
    cta: "Explore emergency response",
    film: FILMS.response,
    align: "end",
    note: "Multi-hazard · Multi-agency context",
  },
] as const;

/* --------------------------------------------------------------------------
   Product proof — real screens
   ----------------------------------------------------------------------- */

export interface ProductShot {
  id: string;
  title: string;
  copy: string;
  image: string;
  alt: string;
  /** Feature the first shot at double width. */
  feature?: boolean;
}

export const PRODUCT_SECTION = {
  eyebrow: "Inside the platform",
  headline: "Nine workspaces. One governed foundation.",
  standfirst:
    "Screens from the running DRISHTI prototype. Every record shown is synthetic demonstration data.",
  cta: "Enter the platform",
} as const;

export const PRODUCT_SHOTS: readonly ProductShot[] = [
  {
    id: "command-center",
    title: "Command Center",
    copy: "Statewide posture, workload and pressure signals for command review.",
    image: "/product/03-command-center.png",
    alt: "DRISHTI Command Center showing operational posture and a Karnataka jurisdiction map",
    feature: true,
  },
  {
    id: "case-explorer",
    title: "Case Explorer",
    copy: "Search, filter and triage the case population across jurisdictions.",
    image: "/product/04-case-explorer.png",
    alt: "DRISHTI Case Explorer listing cases with filters and status columns",
  },
  {
    id: "map",
    title: "Map & Hotspots",
    copy: "District and taluk patterns on real boundaries, traceable to records.",
    image: "/product/05-map-hotspots.png",
    alt: "DRISHTI hotspot map with Karnataka district boundaries and confidence indicators",
  },
  {
    id: "case-file",
    title: "Case File",
    copy: "Timeline, linked people, property and evidence provenance in one record.",
    image: "/product/06-case-file.png",
    alt: "DRISHTI case file with timeline, linked people and evidence provenance",
  },
  {
    id: "board",
    title: "Investigation Board",
    copy: "Working space for hypotheses, leads and the evidence behind each one.",
    image: "/product/07-investigation-board.png",
    alt: "DRISHTI investigation board arranging leads, entities and evidence",
  },
  {
    id: "network",
    title: "Network Analysis",
    copy: "Communities, hidden associations and evidence-backed paths between entities.",
    image: "/product/08-network-analysis.png",
    alt: "DRISHTI network analysis workspace exploring entity relationships",
  },
  {
    id: "analytics",
    title: "Analytics & Forecasting",
    copy: "Labelled forecasts with confidence bounds and model provenance.",
    image: "/product/09-analytics-forecasting.png",
    alt: "DRISHTI analytics workspace with forecast charts and confidence bands",
  },
  {
    id: "ask",
    title: "Ask DRISHTI",
    copy: "Natural-language questions answered with citations to governed records.",
    image: "/product/10-ask-drishti.png",
    alt: "Ask DRISHTI interface showing a natural-language question with cited answers",
  },
  {
    id: "emergency",
    title: "Emergency Response",
    copy: "Live incidents, resources and response plans for multi-hazard events.",
    image: "/product/11-emergency-response.png",
    alt: "DRISHTI emergency response workspace showing a multi-hazard situation overview",
  },
] as const;

/* --------------------------------------------------------------------------
   Audience
   ----------------------------------------------------------------------- */

export interface Audience {
  tier: string;
  roles: string;
  copy: string;
}

export const AUDIENCE_SECTION = {
  eyebrow: "Who it serves",
  headline: "The right picture for every level of command.",
  standfirst:
    "One shared foundation, shaped to the decisions each authorised role is responsible for making.",
} as const;

export const AUDIENCES: readonly Audience[] = [
  {
    tier: "State & range command",
    roles: "DGP · ADGP / IGP",
    copy: "Statewide posture, cross-range comparison and strategic pressure signals.",
  },
  {
    tier: "District & station command",
    roles: "SP · DySP / ACP · SHO",
    copy: "Local workload, jurisdiction integrity and day-to-day coordination.",
  },
  {
    tier: "Investigation & analysis",
    roles: "Investigating Officer · Crime Analyst",
    copy: "Case assembly, entity resolution, networks and evidence trails.",
  },
  {
    tier: "Specialist & governance",
    roles: "Cyber Cell · Traffic Command · System Admin",
    copy: "Specialist intelligence, emergency coordination, model and data governance.",
  },
] as const;

/* --------------------------------------------------------------------------
   Prototype scale
   ----------------------------------------------------------------------- */

export interface Stat {
  value: string;
  label: string;
}

export const STATS: readonly Stat[] = [
  { value: "100,003", label: "case records indexed" },
  { value: "206,026", label: "governed graph records" },
  { value: "32", label: "districts represented" },
  { value: "100%", label: "actions under human review" },
] as const;

export const STATS_SECTION = {
  eyebrow: "Prototype scale",
  headline: "Enough context to judge the system, not just the screen.",
  note: "Inventory from the DRISHTI demonstration dataset. These counts show system scale; every record in this experience is synthetic.",
} as const;

/* --------------------------------------------------------------------------
   Governance
   ----------------------------------------------------------------------- */

export const GOVERNANCE = {
  eyebrow: "Governed by design",
  headline: "Powerful intelligence. Clear boundaries.",
  body: "Predictions are labelled. Uncertainty stays visible. Sensitive records stay inside role and jurisdiction boundaries. DRISHTI strengthens professional judgement, and makes every step inspectable afterwards.",
  sealTitle: "Human authority is never optional",
  sealCopy: "No analytical output creates an operational consequence on its own.",
} as const;

export interface Principle {
  index: string;
  title: string;
  copy: string;
}

export const PRINCIPLES: readonly Principle[] = [
  {
    index: "01",
    title: "Source-aware by default",
    copy: "Every figure, relationship and forecast resolves back to the records it came from.",
  },
  {
    index: "02",
    title: "Scoped to role and jurisdiction",
    copy: "Access follows the command structure and is enforced at the trusted boundary.",
  },
  {
    index: "03",
    title: "Human review before action",
    copy: "Analysis supports a decision; it never becomes the decision-maker.",
  },
  {
    index: "04",
    title: "Accountable after the moment",
    copy: "Queries, model versions, evidence and decisions stay in a complete audit trail.",
  },
] as const;

/* --------------------------------------------------------------------------
   Mission close
   ----------------------------------------------------------------------- */

export const MISSION = {
  eyebrow: "The mission",
  headline: "Intelligence in service of safer communities.",
  body: "A secure operating picture that helps Karnataka's public-safety teams understand events, coordinate across jurisdictions and act with evidence, accountability and human judgement intact.",
  loader: "Establishing the statewide picture",
  strip: "Observe · Understand · Investigate · Decide · Audit",
} as const;

export interface MetaFact {
  label: string;
  value: string;
}

export const MISSION_META: readonly MetaFact[] = [
  { label: "Scope", value: "Statewide context" },
  { label: "Foundation", value: "Governed ontology" },
  { label: "Authority", value: "Human in control" },
] as const;

/* --------------------------------------------------------------------------
   Final CTA and footer
   ----------------------------------------------------------------------- */

export const FINAL_CTA = {
  eyebrow: "The common operating picture is ready",
  /** Closes on the promise the hero opened with, inverted: the hero states the
   *  intent, the footer states what the platform puts in front of you. */
  headline: ["See the whole picture.", "Act on all of it."],
  body: "Enter the synthetic DRISHTI demonstration and explore the platform by operational role.",
  cta: "Enter DRISHTI",
} as const;

export interface FooterColumn {
  heading: string;
  links: readonly NavLink[];
}

export const FOOTER_COLUMNS: readonly FooterColumn[] = [
  {
    heading: "Platform",
    links: [
      { label: "Overview", href: "#platform" },
      { label: "Capabilities", href: "#capabilities" },
      { label: "Inside the product", href: "#product" },
      { label: "Prototype scale", href: "#scale" },
    ],
  },
  {
    heading: "Principles",
    links: [
      { label: "Governance", href: "#governance" },
      { label: "Human in control", href: "#governance" },
      { label: "Who it serves", href: "#audience" },
      { label: "Mission", href: "#mission" },
    ],
  },
  {
    heading: "Access",
    links: [{ label: "Enter the platform", href: "/login" }],
  },
] as const;

export const DISCLOSURE = {
  brandLine: "Decision intelligence for public safety.",
  badge: "Evidence-backed · Human-controlled · Auditable",
  synthetic:
    "Prototype. Every record in this demonstration is synthetic. Predictive output is decision support and must not be read as automatic enforcement.",
  notProduction:
    "This system is not a production criminal-information system and must not be interpreted as one.",
  stack: "React · TypeScript · FastAPI · PostGIS · Zoho Catalyst",
} as const;
