/** DRISHTI public landing page — content model.
 *
 * The page is a product narrative, not a product inventory. Copy stays concise,
 * evidence-led, and explicit about the prototype's synthetic dataset. Nothing in
 * this file should imply autonomous enforcement or production deployment.
 */

/* --------------------------------------------------------------------------
   Media
   ----------------------------------------------------------------------- */

export const MEDIA = {
  heroVideo: "/landing/drishti-hero.mp4",
  heroPoster: "/landing/drishti-hero-poster.webp",
  intelligenceVideo: "/landing/drishti-capability-02.mp4",
  intelligencePoster: "/landing/drishti-capability-02-poster.webp",
  missionVideo: "/landing/drishti-closing-film.mp4",
  missionPoster: "/landing/drishti-closing-poster.webp",
} as const;

export const STILL_FRAMES = {
  hero: 9,
  intelligence: 9.2,
  mission: 5,
} as const;

/* --------------------------------------------------------------------------
   Navigation
   ----------------------------------------------------------------------- */

export interface NavLink {
  label: string;
  href: string;
}

export const NAV_LINKS: readonly NavLink[] = [
  { label: "Platform", href: "#platform" },
  { label: "Capabilities", href: "#capabilities" },
  { label: "Intelligence", href: "#intelligence" },
  { label: "Governance", href: "#governance" },
  { label: "Mission", href: "#mission" },
] as const;

/* --------------------------------------------------------------------------
   Hero
   ----------------------------------------------------------------------- */

export const HERO = {
  eyebrow: "Decision intelligence for public safety",
  headline: ["See the whole picture.", "Decide what", "happens next."],
  standfirst:
    "DRISHTI connects cases, evidence, geography and live incidents into one governed operating picture — so every decision starts with context and ends with accountability.",
  primaryCta: "Enter DRISHTI",
  secondaryCta: "Explore the platform",
  secondaryHref: "#platform",
  scrollCue: "Discover the platform",
  loader: "Connecting the operational picture",
  statusLabel: "Operating principle",
  statusTitle: "One picture. Human judgement.",
} as const;

export interface HeroFact {
  label: string;
  value: string;
}

export const HERO_FACTS: readonly HeroFact[] = [
  { label: "Operating scope", value: "Karnataka, India" },
  { label: "Data foundation", value: "Governed & traceable" },
  { label: "Decision authority", value: "Human in control" },
] as const;

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
    copy: "See statewide posture, live incidents and jurisdiction context together.",
  },
  {
    index: "02",
    name: "Understand",
    copy: "Resolve people, relationships, evidence and geography into one picture.",
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
    copy: "Keep every query, model run and decision accountable after the fact.",
  },
] as const;

/* --------------------------------------------------------------------------
   Platform statement
   ----------------------------------------------------------------------- */

export const PLATFORM = {
  eyebrow: "One operating picture",
  headline: "Fragmented signals become coordinated understanding.",
  body: [
    "Public-safety information arrives in pieces — records, evidence stores, jurisdictions, maps and spreadsheets. The difficult part is not collecting more data. It is understanding what matters together.",
    "DRISHTI connects those pieces without handing judgement to a machine. Sources stay visible, uncertainty stays explicit, and a named person remains responsible for what happens next.",
  ],
  callout: {
    label: "Built for Karnataka's operational context",
    copy: "Every analytical output carries its source, confidence, scope and review status.",
  },
} as const;

/* --------------------------------------------------------------------------
   Product showcase
   ----------------------------------------------------------------------- */

export interface Spotlight {
  id: string;
  eyebrow: string;
  title: string;
  copy: string;
  image: string;
  alt: string;
  span: 5 | 7 | 12;
  wide?: boolean;
}

export const SPOTLIGHTS: readonly Spotlight[] = [
  {
    id: "command",
    eyebrow: "Command Center",
    title: "The state, understood at a glance.",
    copy: "Live posture, workload, emerging pressure and jurisdiction context in one calm, governed view.",
    image: "/product/03-command-center.png",
    alt: "DRISHTI Command Center showing operational posture and a Karnataka jurisdiction map",
    span: 12,
  },
  {
    id: "map",
    eyebrow: "Map & Hotspots",
    title: "Put every signal on the ground.",
    copy: "Explore district and taluk patterns, then trace every hotspot back to the records behind it.",
    image: "/product/05-map-hotspots.png",
    alt: "DRISHTI hotspot map with district boundaries and source confidence",
    span: 5,
  },
  {
    id: "network",
    eyebrow: "Network Analysis",
    title: "Find the connection that changes the case.",
    copy: "Move from an entity to communities, hidden associations, money trails and evidence-backed paths.",
    image: "/product/08-network-analysis.png",
    alt: "DRISHTI network analysis workspace for exploring entity relationships",
    span: 7,
  },
  {
    id: "case",
    eyebrow: "Case Intelligence",
    title: "One case. Every thread intact.",
    copy: "Bring timelines, people, property, digital evidence and financial activity into one reviewable record.",
    image: "/product/06-case-file.png",
    alt: "DRISHTI case file with timeline, linked people and evidence provenance",
    span: 7,
  },
  {
    id: "emergency",
    eyebrow: "Emergency Response",
    title: "Coordinate before pressure becomes crisis.",
    copy: "Unify live incidents, forecast risk, resources and response plans in a dedicated emergency workspace.",
    image: "/product/11-emergency-response.png",
    alt: "DRISHTI emergency response workspace showing a multi-hazard situation overview",
    span: 5,
  },
  {
    id: "ask",
    eyebrow: "Ask DRISHTI",
    title: "Ask plainly. Get an answer you can inspect.",
    copy: "Natural-language questions become scoped, deterministic queries with citations back to governed records — not uncited conclusions.",
    image: "/product/10-ask-drishti.png",
    alt: "Ask DRISHTI interface showing a natural-language question with cited answers",
    span: 12,
    wide: true,
  },
] as const;

export const SPOTLIGHT_SECTION = {
  eyebrow: "The operating system",
  headline: "One platform from first signal to final review.",
  standfirst:
    "Crime intelligence and emergency response share the same governed foundation, so context follows the work instead of disappearing between tools.",
  supportingModules: [
    "Case Explorer",
    "Investigation Board",
    "Analytics & Forecasting",
    "Evidence provenance",
  ],
} as const;

/* --------------------------------------------------------------------------
   Connected intelligence
   ----------------------------------------------------------------------- */

export const INTELLIGENCE = {
  eyebrow: "Connected intelligence",
  headline: "Move from incident to informed action — without losing the evidence chain.",
  body: "DRISHTI assembles the relevant location, people, cases, evidence and model signals into a single explanation before an authorised officer reviews the next move.",
  loader: "Resolving the incident picture",
  caption: "Every connection remains inspectable.",
  panelLabel: "Operational sequence",
  panelTitle: "Karnataka incident intelligence",
  word: "CONNECTED",
} as const;

export interface SequenceStep {
  index: string;
  title: string;
  copy: string;
}

export const SEQUENCE: readonly SequenceStep[] = [
  {
    index: "01",
    title: "Detect the signal",
    copy: "A location-aware incident enters the common operating picture.",
  },
  {
    index: "02",
    title: "Connect the context",
    copy: "Related people, cases, evidence and geography resolve together.",
  },
  {
    index: "03",
    title: "Explain the pattern",
    copy: "Analysis surfaces with provenance, confidence and stated limits.",
  },
  {
    index: "04",
    title: "Review the action",
    copy: "An authorised officer decides what happens next.",
  },
] as const;

export const SEQUENCE_META: readonly HeroFact[] = [
  { label: "Source", value: "Governed records" },
  { label: "Output", value: "Cited analysis" },
  { label: "Control", value: "Human review" },
] as const;

/* --------------------------------------------------------------------------
   Prototype proof
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
  headline: "Enough context to see the system, not just the screen.",
  note: "Prototype inventory from the DRISHTI dataset. These counts demonstrate system scale; every record in this experience is synthetic.",
} as const;

/* --------------------------------------------------------------------------
   Governance
   ----------------------------------------------------------------------- */

export const GOVERNANCE = {
  eyebrow: "Governed by design",
  headline: "Powerful intelligence. Clear boundaries.",
  body: "Predictions are labelled. Uncertainty remains visible. Sensitive records stay inside role and jurisdiction boundaries. DRISHTI strengthens professional judgement — and makes every step inspectable afterwards.",
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
   Mission
   ----------------------------------------------------------------------- */

export const MISSION = {
  eyebrow: "The mission",
  kicker: "Purpose-built for Karnataka",
  bigMark: "Zero",
  bigMarkSuffix: "black boxes",
  headline: "Intelligence in service of safer communities.",
  body: "A secure operating picture that helps public-safety teams understand events, coordinate across jurisdictions and act with evidence, accountability and human judgement intact.",
  loader: "Establishing the statewide picture",
  strip: "Observe · Understand · Investigate · Decide · Audit",
} as const;

export const MISSION_META: readonly HeroFact[] = [
  { label: "Scope", value: "Statewide context" },
  { label: "Foundation", value: "Governed ontology" },
  { label: "Authority", value: "Human in control" },
] as const;

/* --------------------------------------------------------------------------
   Audience
   ----------------------------------------------------------------------- */

export interface Audience {
  tier: string;
  roles: string;
  copy: string;
}

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

export const AUDIENCE_SECTION = {
  eyebrow: "Built around the mission",
  headline: "The right picture for every level of command.",
  standfirst:
    "One shared foundation, shaped to the decisions each authorised role is responsible for making.",
} as const;

/* --------------------------------------------------------------------------
   Final CTA and footer
   ----------------------------------------------------------------------- */

export const FINAL_CTA = {
  eyebrow: "The common operating picture is ready",
  headline: ["See more clearly.", "Act more accountably."],
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
      { label: "Connected intelligence", href: "#intelligence" },
      { label: "Prototype scale", href: "#scale" },
    ],
  },
  {
    heading: "Principles",
    links: [
      { label: "Governance", href: "#governance" },
      { label: "Human in control", href: "#governance" },
      { label: "Mission", href: "#mission" },
      { label: "Audience", href: "#audience" },
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

export const UTILITY_STRIP = {
  left: "Prototype experience · Synthetic demonstration data",
  right: "Karnataka, India",
} as const;
