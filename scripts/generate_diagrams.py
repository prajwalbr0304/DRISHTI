#!/usr/bin/env python3
"""Generate DRISHTI submission diagrams as standalone SVG files.

Produces architecture, wireframe and process-flow diagrams sized for the KSP
Datathon 2026 submission deck (10 x 5.625 in slides, content width 9.10 in).

No third-party dependencies: the SVGs are emitted as text. Rasterise to PNG with
`scripts/rasterise_diagrams.ps1` (Playwright) if PowerPoint-ready bitmaps are
needed, since python-pptx cannot embed SVG.

Usage:
    python scripts/generate_diagrams.py [--out docs/assets/diagrams]
"""
from __future__ import annotations

import argparse
import html
from pathlib import Path

# --- design tokens (mirror KSP-Datathon-2026-PPT-Agent-Brief.md section 2.1) ---
INK = "#111827"
DIM = "#4B5563"
RULE = "#D1D5DB"
SURFACE = "#F3F4F6"
WHITE = "#FFFFFF"
PRIMARY = "#0B6CFB"
TEAL = "#0E9F8C"
AMBER = "#B45309"
INDIGO = "#4338CA"
FONT = "Segoe UI,Inter,Helvetica Neue,Arial,sans-serif"
MONO = "Cascadia Mono,Consolas,monospace"


# --------------------------------------------------------------------------- #
# minimal SVG builder
# --------------------------------------------------------------------------- #
class Svg:
    def __init__(self, w: int, h: int, title: str):
        self.w, self.h, self.title = w, h, title
        self.parts: list[str] = []

    # -- primitives ---------------------------------------------------------
    def rect(self, x, y, w, h, fill=WHITE, stroke=RULE, sw=1.2, r=6, dash=None,
             opacity=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        o = f' fill-opacity="{opacity}"' if opacity is not None else ""
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}{o}/>')

    def line(self, x1, y1, x2, y2, stroke=DIM, sw=1.4, dash=None, arrow=True,
             marker="arrow"):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        a = f' marker-end="url(#{marker})"' if arrow else ""
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" '
            f'stroke-width="{sw}" stroke-linecap="round"{d}{a}/>')

    def path(self, d, stroke=DIM, sw=1.4, fill="none", dash=None, arrow=True,
             marker="arrow"):
        da = f' stroke-dasharray="{dash}"' if dash else ""
        a = f' marker-end="url(#{marker})"' if arrow else ""
        self.parts.append(
            f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" '
            f'stroke-linejoin="round" stroke-linecap="round"{da}{a}/>')

    def poly(self, pts, fill=WHITE, stroke=RULE, sw=1.2):
        p = " ".join(f"{x},{y}" for x, y in pts)
        self.parts.append(f'<polygon points="{p}" fill="{fill}" '
                          f'stroke="{stroke}" stroke-width="{sw}"/>')

    def text(self, x, y, s, size=13, fill=INK, weight="400", anchor="start",
             font=None, spacing=None, italic=False):
        ls = f' letter-spacing="{spacing}"' if spacing else ""
        it = ' font-style="italic"' if italic else ""
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{font or FONT}" '
            f'font-size="{size}" fill="{fill}" font-weight="{weight}" '
            f'text-anchor="{anchor}"{ls}{it}>{html.escape(s)}</text>')

    # -- composites ---------------------------------------------------------
    def wrap(self, x, y, s, size=12, fill=INK, weight="400", anchor="start",
             width_chars=30, lh=None, font=None):
        """Naive character-count wrapper. Returns the y of the last baseline."""
        lh = lh or size + 3
        words, line, lines = s.split(), "", []
        for w in words:
            cand = f"{line} {w}".strip()
            if len(cand) > width_chars and line:
                lines.append(line)
                line = w
            else:
                line = cand
        if line:
            lines.append(line)
        for i, ln in enumerate(lines):
            self.text(x, y + i * lh, ln, size=size, fill=fill, weight=weight,
                      anchor=anchor, font=font)
        return y + (len(lines) - 1) * lh

    def box(self, x, y, w, h, title, body=None, fill=WHITE, stroke=RULE,
            accent=None, tsize=13, bsize=11, r=6, chars=None, dash=None):
        """Card with an optional 3px left accent bar and wrapped body text."""
        self.rect(x, y, w, h, fill=fill, stroke=stroke, r=r, dash=dash)
        if accent:
            self.parts.append(
                f'<path d="M{x + 3} {y + 2} L{x + 3} {y + h - 2}" '
                f'stroke="{accent}" stroke-width="3.4" stroke-linecap="round"/>')
        pad = 11 if accent else 9
        ty = y + tsize + 7
        self.wrap(x + pad, ty, title, size=tsize, weight="700", fill=INK,
                  width_chars=chars or max(8, int(w / (tsize * 0.55))))
        if body:
            self.wrap(x + pad, ty + tsize + 6, body, size=bsize, fill=DIM,
                      width_chars=int(w / (bsize * 0.52)))

    def zone(self, x, y, w, h, label, stroke=RULE, fill=None, lcolour=None):
        self.rect(x, y, w, h, fill=fill or "none", stroke=stroke, sw=1.3, r=10,
                  dash="5 4", opacity=1 if fill else None)
        self.text(x + 12, y + 17, label.upper(), size=10.5, weight="700",
                  fill=lcolour or DIM, spacing="0.9")

    def diamond(self, cx, cy, w, h, label, stroke=PRIMARY, fill=WHITE, size=11):
        self.poly([(cx, cy - h / 2), (cx + w / 2, cy), (cx, cy + h / 2),
                   (cx - w / 2, cy)], fill=fill, stroke=stroke, sw=1.5)
        self.wrap(cx, cy - 2, label, size=size, weight="700", anchor="middle",
                  width_chars=16)

    def pill(self, x, y, w, h, label, fill=SURFACE, stroke=RULE, colour=INK,
             size=10.5, weight="600"):
        self.rect(x, y, w, h, fill=fill, stroke=stroke, r=h / 2, sw=1)
        self.text(x + w / 2, y + h / 2 + size * 0.36, label, size=size,
                  fill=colour, weight=weight, anchor="middle")

    def kicker(self, x, y, s, colour=PRIMARY):
        self.text(x, y, s.upper(), size=10.5, weight="700", fill=colour,
                  spacing="1.1")

    def caption(self, x, y, s, size=10, anchor="start"):
        self.text(x, y, s, size=size, fill=DIM, anchor=anchor, italic=True)

    # -- output -------------------------------------------------------------
    def render(self) -> str:
        defs = (
            '<defs>'
            '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0 L10 5 L0 10 z" fill="{DIM}"/></marker>'
            '<marker id="arrowP" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0 L10 5 L0 10 z" fill="{PRIMARY}"/></marker>'
            '<marker id="arrowT" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0 L10 5 L0 10 z" fill="{TEAL}"/></marker>'
            '<marker id="arrowA" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0 L10 5 L0 10 z" fill="{AMBER}"/></marker>'
            '</defs>')
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" '
            f'height="{self.h}" viewBox="0 0 {self.w} {self.h}" '
            f'role="img" aria-label="{html.escape(self.title)}">'
            f'<title>{html.escape(self.title)}</title>{defs}'
            f'<rect width="{self.w}" height="{self.h}" fill="{WHITE}"/>'
            + "".join(self.parts) + "</svg>")

    def save(self, path: Path):
        path.write_text(self.render(), encoding="utf-8")
        print(f"  wrote {path.as_posix()}  ({self.w}x{self.h})")


def head(s: Svg, title: str, sub: str = ""):
    s.text(28, 34, title, size=19, weight="700", fill=INK)
    if sub:
        s.text(28, 55, sub, size=11.5, fill=DIM)
    s.line(28, 66, s.w - 28, 66, stroke=RULE, sw=1, arrow=False)


def foot(s: Svg, note: str):
    s.caption(28, s.h - 14, note, size=10)


# =========================================================================== #
# 1. ARCHITECTURE
# =========================================================================== #
def arch_system(out: Path):
    s = Svg(1840, 950, "DRISHTI system architecture")
    head(s, "DRISHTI — solution architecture",
         "Browser → Zoho Catalyst trusted edge → Catalyst operational services, "
         "with a protected server-to-server analytical plane. No browser ever "
         "holds a database credential.")

    # --- users -------------------------------------------------------------
    s.zone(28, 86, 246, 470, "Public-safety users", lcolour=INK)
    users = [
        ("State / Senior command", "DGP · ADGP wing · DIG range"),
        ("District command & SHO", "SP · CP · station chief"),
        ("Investigating officers", "assigned cases, evidence, leads"),
        ("Cyber, traffic, emergency", "wings and response command"),
        ("System & model admins", "seats, roles, registry, audit"),
    ]
    for i, (t, b) in enumerate(users):
        s.box(44, 112 + i * 88, 214, 74, t, b, fill=SURFACE, accent=PRIMARY,
              tsize=12, bsize=10)

    # --- catalyst edge -----------------------------------------------------
    s.zone(300, 86, 470, 470, "Zoho Catalyst — trusted operational edge",
           stroke=PRIMARY, lcolour=PRIMARY)
    s.box(318, 112, 434, 66, "Catalyst Slate",
          "React 18.3 + TypeScript SPA · 39 role-scoped routes · SPA redirects",
          accent=PRIMARY, tsize=13, bsize=10)
    s.box(318, 188, 210, 66, "Catalyst Authentication",
          "Session identity; role from directory attribute",
          accent=PRIMARY, tsize=12, bsize=9.5)
    s.box(542, 188, 210, 66, "Catalyst API Gateway",
          "3 routes · sliding window 600/min, 120/min per IP",
          accent=PRIMARY, tsize=12, bsize=9.5)
    s.box(318, 264, 434, 104, "gateway_api function  (Advanced I/O, Node 20)",
          "Derives role + scope SERVER-SIDE · strips 9 spoofable identity headers "
          "and every x-drishti-* header · mints a 60-second HMAC-SHA256 signed "
          "context (aud drishti-appsail, nonce, request id)",
          fill="#EFF6FF", accent=PRIMARY, tsize=12.5, bsize=10)
    s.box(318, 386, 434, 96, "Catalyst AppSail — drishti-api",
          "FastAPI 0.115 on python:3.12-slim, custom OCI, port 9000, 512 MB, "
          "1 pinned instance · 37 routers / 391 endpoints · VERIFIES signature, "
          "audience, scope, expiry and nonce replay before any non-health request",
          fill="#EFF6FF", accent=PRIMARY, tsize=12.5, bsize=10)
    s.box(318, 492, 434, 50, "8 further Catalyst functions",
          "channel_token · 4 event functions · notify_dispatch · 2 crons",
          fill=SURFACE, accent=DIM, tsize=11.5, bsize=9.5)

    # --- catalyst services -------------------------------------------------
    s.zone(796, 86, 494, 470, "Zoho Catalyst — operational services",
           stroke=TEAL, lcolour=TEAL)
    svc = [
        ("Data Store", "106 idempotent import configs + 20 native tables "
                       "(6 board, 14 hazard)"),
        ("Stratus", "3 private versioned buckets; 900 s pre-signed exact-object URLs"),
        ("Cache · NoSQL", "idempotency, rate limit, nonce, lookup · layouts, presence"),
        ("Signals · Cron", "1 minimal Signal (prediction-requested) · 1 daily forecast cron"),
        ("QuickML", "no-code workload baseline · RAG over 6 approved SOP sources"),
        ("Pipelines", "10 jobs / 6 stages: validate → build → security → preflight → deploy → smoke"),
    ]
    for i, (t, b) in enumerate(svc):
        s.box(814, 112 + i * 74, 458, 62, t, b, fill=WHITE, accent=TEAL,
              tsize=12, bsize=9.5)

    # --- protected AWS plane -----------------------------------------------
    s.zone(1316, 86, 496, 470,
           "Protected analytical plane — server-to-server only",
           stroke=AMBER, lcolour=AMBER)
    s.box(1334, 112, 460, 62, "Signed AWS adapter (Lambda arm64)",
          "HMAC over ts|nonce|body · rate limiter · circuit breaker · audit",
          fill="#FFFBEB", accent=AMBER, tsize=12, bsize=9.5)
    aws = [
        ("PostgreSQL 17.10 + PostGIS + pgvector",
         "140 tables · 3,011,145 rows · 1.02 GB · HNSW cosine ANN"),
        ("Private S3 + KMS",
         "Digital evidence objects and model artifacts"),
        ("SageMaker async GPU (scale-to-zero)",
         "TabFM · TimesFM 2.5-200M · ST-GNN — fails closed off CUDA"),
        ("Bedrock zai.glm-4.7-flash",
         "Ask DRISHTI semantic planner behind the signed adapter"),
        ("Bedrock Nova 2 Sonic + AgentCore",
         "Duplex voice transport only; answers stay in Zoho"),
    ]
    for i, (t, b) in enumerate(aws):
        s.box(1334, 186 + i * 74, 460, 62, t, b, fill=WHITE, accent=AMBER,
              tsize=11.5, bsize=9.5)

    # --- arrows ------------------------------------------------------------
    s.line(258, 260, 316, 200, stroke=PRIMARY, sw=1.7, marker="arrowP")
    s.line(536, 178, 536, 186, stroke=PRIMARY, sw=1.7, marker="arrowP")
    s.line(423, 254, 423, 262, stroke=PRIMARY, sw=1.7, marker="arrowP")
    s.line(536, 368, 536, 382, stroke=PRIMARY, sw=2.4, marker="arrowP")
    # AppSail -> Catalyst services (short hop in the inter-zone gutter).
    s.line(756, 300, 792, 300, stroke=TEAL, sw=2.2, marker="arrowT")
    # AppSail -> protected AWS plane. Routed BELOW both zones so it never
    # crosses a service card.
    s.path("M600 482 L600 578 L1564 578 L1564 560", stroke=AMBER, sw=2.2,
           marker="arrowA")
    s.rect(760, 562, 646, 17, fill=WHITE, stroke="none", sw=0, r=2)
    s.text(1083, 575, "HTTPS + HMAC over ts|nonce|body — no AWS keys on AppSail",
           size=10.5, fill=AMBER, weight="700", anchor="middle")
    s.line(1274, 300, 1332, 148, stroke=AMBER, sw=1.8, marker="arrowA")

    # --- arrow legend ------------------------------------------------------
    for i, (col, mk, lab) in enumerate([
            (PRIMARY, "arrowP", "Signed identity path"),
            (TEAL, "arrowT", "Catalyst SDK (server-side)"),
            (AMBER, "arrowA", "Protected server-to-server only")]):
        x = 1180 + i * 220
        s.line(x, 50, x + 26, 50, stroke=col, sw=2.2, marker=mk)
        s.text(x + 32, 54, lab, size=9.8, fill=col, weight="600")

    # --- governance strip --------------------------------------------------
    s.zone(28, 592, 1784, 106, "Cross-cutting governance", lcolour=INDIGO,
           stroke=INDIGO)
    gov = [
        ("Append-only audit", "Written transactionally with the action; "
                              "sensitive keys stripped"),
        ("Model registry", "Version, feature snapshot, backtest, human review"),
        ("Scope & purpose guards", "Role × 9 scope types · jurisdiction · "
                                   "rate · payload"),
        ("Read-only SQL guard", "drishti_readonly role, read-only txn, "
                                "deny-lists, row cap"),
        ("Synthetic-data policy", "Boot refuses a non-synthetic database marker"),
    ]
    for i, (t, b) in enumerate(gov):
        s.box(44 + i * 354, 618, 338, 66, t, b, fill="#EEF2FF", accent=INDIGO,
              tsize=11.5, bsize=9.5)

    # --- boundary rules ----------------------------------------------------
    s.text(28, 742, "Trust boundaries enforced in code", size=13,
           weight="700", fill=INK)
    rules = [
        ("Browser → Catalyst",
         "Public config only. A release build FAILS on a Postgres URL, PEM key, "
         "AKIA id or any amazonaws.com URL in dist/."),
        ("Gateway → AppSail",
         "Client identity headers stripped, then a signed 60 s context injected. "
         "Unsigned requests get an opaque 401."),
        ("AppSail → analytics",
         "Only the backend reaches PostgreSQL, private object storage or GPU "
         "inference. The browser has no path to AWS."),
        ("Model → action",
         "No model may dispatch, accuse, arrest, close a case or modify a "
         "protected record. Human review is mandatory."),
    ]
    for i, (t, b) in enumerate(rules):
        x = 28 + i * 452
        s.rect(x, 756, 436, 78, fill=SURFACE, stroke=RULE, r=6)
        s.text(x + 12, 776, t, size=11.5, weight="700", fill=PRIMARY)
        s.wrap(x + 12, 792, b, size=9.8, fill=DIM, width_chars=62)

    foot(s, "Verified 6 Sep 2026: Slate HTTP 200 · API Gateway /api/health 200 "
            "(database true, postgis/vector/pg_trgm/pgrouting present) · AppSail "
            "/health/ready 200 ready=true, environment synthetic_hackathon. "
            "All records are synthetic demonstration data.")
    s.save(out / "arch-01-system.svg")


def arch_request(out: Path):
    s = Svg(1840, 596, "DRISHTI request lifecycle and trust boundaries")
    head(s, "Request lifecycle — how one API call is authorised",
         "Ten steps from browser click to rendered answer. Identity is derived "
         "server-side at step 5 and verified again at step 6.")

    # Tier legend (the swimlane a step belongs to is shown by its accent bar,
    # which keeps every card the same size and every label on one line).
    tiers = [("Browser", PRIMARY), ("Catalyst edge", INDIGO),
             ("AppSail domain service", TEAL), ("Governed data", AMBER)]
    for i, (name, col) in enumerate(tiers):
        x = 900 + i * 236
        s.rect(x, 42, 12, 16, fill=col, stroke="none", sw=0, r=3)
        s.text(x + 20, 55, name, size=10, fill=col, weight="600")

    steps = [
        (1, PRIMARY, "Open the Slate app",
         "The React SPA loads with public configuration only — no credential, "
         "endpoint secret or role is present in the bundle."),
        (2, PRIMARY, "Catalyst Authentication",
         "The session establishes who the user is. The client never asserts a "
         "role; it has nothing to assert it with."),
        (3, PRIMARY, "SPA calls /api/*",
         "The Catalyst API Gateway origin is the only public API path. Nothing "
         "in the browser addresses AppSail or AWS."),
        (4, INDIGO, "API Gateway invokes gateway_api",
         "Sliding-window throttle: 600 requests/min overall, 120/min per IP. "
         "AppSail is not a native gateway target, so the function fronts it."),
        (5, INDIGO, "Gateway derives and signs identity",
         "Strips 9 spoofable identity headers, resolves role and scope from the "
         "directory server-side, mints a 60-second HMAC-SHA256 context."),
        (6, TEAL, "AppSail verifies the context",
         "Signature, audience, scope, expiry and nonce replay are all checked "
         "before routing. Any failure returns an opaque 401."),
        (7, TEAL, "Domain policy applied",
         "Role, jurisdiction, purpose, rate and payload guards run. "
         "Aggregate-only seats are refused case-level detail here."),
        (8, AMBER, "Scoped read served",
         "From the curated Catalyst operational layer and, where authorised, "
         "the protected analytical plane behind the signed adapter."),
        (9, AMBER, "Provenance written",
         "Material writes and model outputs append audit or model-provenance "
         "evidence, transactionally with the action itself."),
        (10, PRIMARY, "UI renders with context",
         "Scope, data freshness, confidence and source indicators are shown "
         "beside the answer — never a bare number."),
    ]
    for i, (n, col, t, b) in enumerate(steps):
        x = 28 + (i % 5) * 362
        y = 100 + (i // 5) * 182
        s.rect(x, y, 340, 152, fill=WHITE, stroke=RULE, r=8)
        s.parts.append(f'<path d="M{x + 3} {y + 2} L{x + 3} {y + 150}" '
                       f'stroke="{col}" stroke-width="3.6" '
                       f'stroke-linecap="round"/>')
        s.parts.append(f'<circle cx="{x + 30} " cy="{y + 26}" r="13" '
                       f'fill="{col}"/>')
        s.text(x + 30, y + 31, str(n), size=11.5, weight="700", fill=WHITE,
               anchor="middle")
        s.wrap(x + 52, y + 25, t, size=11.8, weight="700", width_chars=26)
        s.wrap(x + 16, y + 72, b, size=9.6, fill=DIM, width_chars=48)
        if i % 5 < 4:
            s.line(x + 344, y + 76, x + 358, y + 76, stroke=col, sw=2,
                   marker="arrowP" if col in (PRIMARY, INDIGO) else "arrow")
    # wrap from step 5 down to step 6
    s.path("M1638 252 L1638 268 L198 268 L198 280", stroke=INDIGO, sw=1.8,
           marker="arrowP")

    s.text(28, 490, "What cannot happen", size=13, weight="700", fill=INK)
    nos = [
        "The browser cannot forge a role — only the gateway holds the signing secret.",
        "A direct unauthenticated call to the AppSail URL is rejected 401 (non-health routes).",
        "A 401 never reveals which check failed, so it cannot be used as an oracle.",
        "A nonce is consumed exactly once; replay is caught in-process and in Catalyst Cache.",
    ]
    for i, t in enumerate(nos):
        x = 28 + i * 452
        s.rect(x, 500, 436, 62, fill=SURFACE, stroke=RULE, r=6)
        s.text(x + 14, 524, "✕", size=13, weight="700", fill=AMBER)
        s.wrap(x + 34, 522, t, size=9.8, fill=DIM, width_chars=56)
    foot(s, "The gateway is the only holder of the signing secret, which is why "
            "role forgery is structurally impossible rather than merely "
            "validated. Verified live 6 Sep 2026.")
    s.save(out / "arch-02-request-lifecycle.svg")


def arch_data(out: Path):
    s = Svg(1840, 700, "DRISHTI data architecture")
    head(s, "Data architecture — one ontology, two serving planes",
         "Synthetic sources are validated into a canonical ontology, then split: "
         "a curated operational plane on Catalyst and a protected analytical "
         "plane on AWS.")

    stages = [
        ("Synthetic source datasets",
         "FIR, parties, evidence, property, transactions, stations, hazards. "
         "Deterministic: seed 42, 2021-01-01 → 2025-12-31, 41 generator modules",
         PRIMARY),
        ("Validation and data quality",
         "Schema, referential and jurisdiction rules. Failures are staged as "
         "reviewable DataQualityIssues, never silently repaired",
         PRIMARY),
        ("Canonical ontology + relationships",
         "Typed objects: case, person, party role, station, evidence, "
         "transaction, property, statement, lifecycle event — direction and "
         "source preserved",
         INDIGO),
    ]
    for i, (t, b, c) in enumerate(stages):
        x = 28 + i * 470
        s.box(x, 92, 440, 96, t, b, fill=SURFACE, accent=c, tsize=13, bsize=10)
        if i < 2:
            s.line(x + 444, 140, x + 466, 140, stroke=DIM, sw=1.8)

    s.line(1438, 140, 1460, 140, stroke=DIM, sw=1.8)
    s.box(1468, 92, 344, 96, "Immutable feature snapshots",
          "Every prediction binds to a snapshot id, source cutoff and feature "
          "schema version, so a forecast is reproducible",
          fill="#EEF2FF", accent=INDIGO, tsize=13, bsize=10)

    # two planes
    s.zone(28, 216, 880, 250, "Curated operational plane — Zoho Catalyst",
           stroke=TEAL, lcolour=TEAL)
    s.box(46, 246, 410, 92, "Curated serving-subset exporter",
          "Golden seed cases first, then deterministic fill; children FK-scoped "
          "to the seed; sensitive columns dropped; content SHA-256 per table",
          accent=TEAL, tsize=12, bsize=9.8)
    s.box(476, 246, 414, 92, "Catalyst Data Store",
          "106 idempotent import configs, upsert on ExternalID, dev cap 5,000 "
          "rows/table · 20 Data-Store-native tables for Board and Hazard",
          accent=TEAL, tsize=12, bsize=9.8)
    s.box(46, 352, 844, 96, "Reconciliation",
          "Count, content-hash and mapping-version parity plus referential "
          "resolution are checked against the Data Store; the import-config "
          "generator fails closed on mapping drift in CI.",
          fill=WHITE, accent=TEAL, tsize=12, bsize=9.8)

    s.zone(932, 216, 880, 250, "Protected analytical plane — AWS",
           stroke=AMBER, lcolour=AMBER)
    s.box(950, 246, 410, 92, "PostgreSQL 17.10 + PostGIS + pgvector",
          "140 tables · 3,011,145 exact rows · 1.02 GB · 503 indexes · "
          "20 views + 3 materialized views · 7 extensions",
          accent=AMBER, tsize=12, bsize=9.8)
    s.box(1380, 246, 414, 92, "Private object + model storage",
          "S3 with KMS for evidence objects and model artifacts; immutable ECR "
          "tags; async I/O prefixes expire after 7 days",
          accent=AMBER, tsize=12, bsize=9.8)
    s.box(950, 352, 844, 96, "Reachable only server-to-server",
          "The signed adapter is the sole path. Only ids, versions, hashes and "
          "feature vectors cross the boundary — never narrative text, PII or a "
          "connection string. RDS is not publicly reachable in the target posture.",
          fill=WHITE, accent=AMBER, tsize=12, bsize=9.8)

    s.line(468, 466, 468, 496, stroke=TEAL, sw=1.8, marker="arrowT")
    s.line(1372, 466, 1372, 496, stroke=AMBER, sw=1.8, marker="arrowA")

    s.box(28, 502, 880, 84, "FastAPI domain services",
          "37 registered routers · 391 endpoints · every AI endpoint returns the "
          "same contract: answer, confidence 0–1, source_record_ids[], "
          "reasoning_summary (never chain-of-thought), model_version",
          fill="#EFF6FF", accent=PRIMARY, tsize=13, bsize=10)
    s.box(932, 502, 880, 84, "Role-scoped React application",
          "39 declared routes · 18 destinations across 2 workspaces · surface "
          "chosen by role, data chosen by seat scope; the server re-derives "
          "access on every request",
          fill="#EFF6FF", accent=PRIMARY, tsize=13, bsize=10)
    s.line(908, 544, 928, 544, stroke=PRIMARY, sw=1.8, marker="arrowP")

    s.box(28, 600, 1784, 62, "Audit, snapshots, model provenance and evidence trail",
          "Append-only. Audit rows are written transactionally with the action, "
          "so a rolled-back action rolls back its audit; passwords, narratives, "
          "date of birth, phone, Aadhaar and coordinates are stripped before storage.",
          fill="#EEF2FF", accent=INDIGO, tsize=12.5, bsize=10)
    foot(s, "Row counts measured 26 Jul 2026 by exact COUNT(*) over every "
            "ordinary user table. All data are synthetic.")
    s.save(out / "arch-03-data.svg")


# =========================================================================== #
# 2. WIREFRAMES
# =========================================================================== #
def _wf_frame(s: Svg, title: str, caption: str):
    s.rect(10, 10, s.w - 20, s.h - 40, fill=WHITE, stroke=INK, sw=1.6, r=8)
    s.text(22, 34, title, size=14, weight="700", fill=INK)
    s.caption(12, s.h - 12, caption, size=10.5)


def wire_login(out: Path):
    s = Svg(1300, 540, "Wireframe — role-scoped sign-in")
    _wf_frame(s, "Wireframe · Role-scoped sign-in",
              "Role selects the SURFACE. Seat scope selects the DATA. They are "
              "orthogonal axes — that is why ADGP and DIG share one role.")
    s.line(650, 46, 650, 494, stroke=RULE, sw=1.4, arrow=False)

    s.rect(36, 62, 590, 34, fill=INK, stroke=INK, r=5)
    s.text(50, 84, "DRISHTI", size=14, weight="700", fill=WHITE)
    s.text(132, 84, "Decision Intelligence for Public Safety", size=10.5,
           fill="#D1D5DB")
    s.kicker(36, 128, "One operational picture")
    s.wrap(36, 156, "From first signal to reviewed action.", size=17,
           weight="700", width_chars=34)
    s.wrap(36, 200, "Crime records, people, property, digital and financial "
                    "evidence, geography, live events and forecasts in one "
                    "governed interface.", size=11, fill=DIM, width_chars=62)
    s.box(36, 262, 286, 74, "Crime Intelligence",
          "FIRs, people, networks, hotspots, forecasting", accent=PRIMARY,
          fill=SURFACE, tsize=12, bsize=9.5)
    s.box(340, 262, 286, 74, "Emergency Response",
          "Multi-hazard forecasting, readiness, evacuation", accent=INDIGO,
          fill=SURFACE, tsize=12, bsize=9.5)
    for i, t in enumerate(["Evidence-backed", "Human-controlled",
                           "Fully auditable", "Synthetic demo data"]):
        s.pill(36 + i * 150, 356, 138, 24, t, colour=DIM)
    s.rect(36, 398, 590, 78, fill="#EFF6FF", stroke=PRIMARY, r=6)
    s.text(50, 422, "Deployed on Zoho Catalyst", size=11.5, weight="700",
           fill=PRIMARY)
    s.wrap(50, 442, "Catalyst Authentication establishes identity. The API "
                    "Gateway is the only public API origin. The browser holds "
                    "no database credential.", size=9.8, fill=DIM,
           width_chars=74)

    s.text(676, 84, "Choose your operational seat", size=14, weight="700")
    s.rect(676, 100, 590, 30, fill=SURFACE, stroke=RULE, r=15)
    s.text(692, 120, "⌕  Search 11,800 seats by name, rank, district or station",
           size=10, fill=DIM)
    seats = [
        ("DGP / State Command", "DGP Vikram Shetty", "State · all districts",
         "Aggregate only"),
        ("Senior Command", "IGP Meenakshi Rao", "Wing (state-wide) or Range",
         "ADGP wing / DIG range"),
        ("District Command", "SP Anand Kumar", "District or Commissionerate",
         "All stations"),
        ("SHO", "SHO Suresh Patil", "Station · all station cases",
         "Registration + review"),
        ("Investigating Officer", "PSI Ramesh Gowda", "Assigned cases",
         "Own station"),
        ("System Admin", "Sysadmin Nikhil Jain", "Platform administration",
         "Seats, roles, registry"),
    ]
    for i, (role, who, scope, note) in enumerate(seats):
        x, y = 676 + (i % 2) * 300, 146 + (i // 2) * 84
        s.rect(x, y, 288, 74, fill=WHITE, stroke=RULE, r=6)
        s.parts.append(f'<path d="M{x + 3} {y + 2} L{x + 3} {y + 72}" '
                       f'stroke="{PRIMARY}" stroke-width="3.4" '
                       f'stroke-linecap="round"/>')
        s.text(x + 14, y + 20, role, size=11.5, weight="700")
        s.text(x + 14, y + 36, who, size=10, fill=DIM)
        s.text(x + 14, y + 52, scope, size=9.5, fill=PRIMARY, weight="600")
        s.text(x + 14, y + 66, note, size=9, fill=DIM, italic=True)
    s.rect(676, 402, 590, 74, fill=SURFACE, stroke=AMBER, r=6)
    s.text(690, 424, "Six application roles, nine scope types", size=11,
           weight="700", fill=AMBER)
    s.wrap(690, 442, "A role answers one question — which surface to render. "
                     "Scope is resolved server-side from the seat's posting. An "
                     "unposted seat resolves to 'unresolved' and sees nothing, "
                     "never state-wide.", size=9.6, fill=DIM, width_chars=78)
    s.save(out / "wire-01-login.svg")


def wire_shell(out: Path):
    s = Svg(1300, 540, "Wireframe — application shell")
    _wf_frame(s, "Wireframe · Application shell",
              "18 destinations in 5 sections, filtered by workspace context, "
              "admin flag and seat scope. Rendering is not the authorisation "
              "boundary — the server re-derives access per request.")

    # sidebar
    s.rect(24, 50, 236, 440, fill=SURFACE, stroke=RULE, r=6)
    s.rect(36, 60, 212, 40, fill=WHITE, stroke=RULE, r=5)
    s.text(48, 78, "DRISHTI", size=12.5, weight="700")
    s.text(48, 92, "Crime Intelligence", size=9.5, fill=DIM)
    s.rect(36, 108, 212, 28, fill=WHITE, stroke=PRIMARY, r=5)
    s.text(48, 126, "⇅  Workspace switcher", size=9.8, fill=PRIMARY,
           weight="600")
    nav = [
        ("Overview", ["Command Center"]),
        ("Case work", ["Cases", "Intake", "People & Entities",
                       "Face Recognition"]),
        ("Analysis", ["Network Analysis", "Investigation Board",
                      "Map & Hotspots", "Live Watch Wall",
                      "Analytics & Forecasting"]),
        ("Assistant", ["Ask DRISHTI"]),
        ("Administration", ["Support", "Admin"]),
    ]
    y = 152
    for section, items in nav:
        s.text(44, y, section, size=9.8, weight="700", fill=INK)
        y += 15
        for it in items:
            active = it == "Command Center"
            if active:
                s.rect(38, y - 10, 208, 17, fill="#DBEAFE", stroke="none",
                       sw=0, r=4)
            s.text(50, y + 2, "▸ " + it, size=9.4,
                   fill=PRIMARY if active else DIM,
                   weight="700" if active else "400")
            y += 18
        y += 6

    # top bar
    s.rect(272, 50, 1004, 40, fill=WHITE, stroke=RULE, r=6)
    s.rect(286, 58, 300, 24, fill=SURFACE, stroke=RULE, r=12)
    s.text(298, 74, "⌘K  Search cases, people, places, evidence", size=9.4,
           fill=DIM)
    for i, t in enumerate(["Time window", "Region", "Alerts 3", "Theme",
                           "EN / ಕನ್ನಡ", "Profile · scope"]):
        s.pill(600 + i * 112, 58, 104, 24, t, colour=DIM, size=9.2)
    s.rect(272, 96, 1004, 24, fill=SURFACE, stroke=RULE, r=4)
    s.text(284, 112, "Command Center  ›  District · Bengaluru City  ›  "
                     "Last 90 days", size=9.6, fill=DIM)

    # body
    s.rect(272, 128, 800, 362, fill=WHITE, stroke=RULE, r=6)
    s.text(286, 148, "Active workspace — role-adaptive widget set", size=11.5,
           weight="700")
    s.caption(286, 164, "The widget SET is swapped per role, not relabelled. "
                        "Cards are drag/resize on a persisted grid.", size=9.2)
    kpis = [("Incidents", "window · YoY"), ("Open cases", "in scope"),
            ("Critical alerts", "unactioned"), ("Chargesheet", "throughput")]
    for i, (t, b) in enumerate(kpis):
        x = 286 + i * 194
        s.rect(x, 176, 182, 62, fill=SURFACE, stroke=RULE, r=5)
        s.text(x + 12, 198, "0,000", size=17, weight="700", fill=PRIMARY)
        s.text(x + 12, 214, t, size=9.8, weight="600")
        s.text(x + 12, 228, b, size=8.8, fill=DIM)
    panels = [("Jurisdiction trend", "line · anomalous periods flagged"),
              ("Hotspots in scope", "map · click to open the case"),
              ("Case ageing", "bar · over 180 days"),
              ("Recent activity", "table · source and actor")]
    for i, (t, b) in enumerate(panels):
        x, y2 = 286 + (i % 2) * 388, 250 + (i // 2) * 116
        s.rect(x, y2, 376, 104, fill=WHITE, stroke=RULE, r=5)
        s.text(x + 12, y2 + 20, t, size=10.5, weight="700")
        s.text(x + 12, y2 + 35, b, size=9, fill=DIM)
        s.rect(x + 12, y2 + 44, 352, 48, fill=SURFACE, stroke=RULE, r=4,
               dash="4 3")

    # peek rail
    s.rect(1084, 128, 192, 362, fill=SURFACE, stroke=RULE, r=6)
    s.text(1096, 148, "Peek rail", size=10.5, weight="700")
    for i, t in enumerate(["Selected object", "Source & provenance",
                           "Pinned snapshot", "Related records",
                           "Data freshness", "Send to board"]):
        s.rect(1096, 158 + i * 54, 168, 46, fill=WHITE, stroke=RULE, r=5)
        s.text(1106, 178 + i * 54, t, size=9.4, weight="600")
        s.text(1106, 192 + i * 54, "— governed reference —", size=8.4, fill=DIM)
    s.save(out / "wire-02-app-shell.svg")


def wire_map(out: Path):
    s = Svg(1300, 540, "Wireframe — Map and Hotspots")
    _wf_frame(s, "Wireframe · Map & Hotspots",
              "A marker is a traceable record, not decoration. Aggregate-only "
              "seats are narrowed to Forecast; the SHO-region overlay is not "
              "aggregate-safe.")
    modes = ["Live Map", "Hotspots", "Forecast", "Patrol Planning",
             "Red-Zone Alerts"]
    for i, m in enumerate(modes):
        act = i == 0
        s.pill(30 + i * 132, 52, 124, 26, m,
               fill="#DBEAFE" if act else SURFACE,
               stroke=PRIMARY if act else RULE,
               colour=PRIMARY if act else DIM)
    s.pill(700, 52, 40, 26, "⛶", colour=DIM)

    s.rect(30, 90, 214, 400, fill=SURFACE, stroke=RULE, r=6)
    ctrl = [("Basemap", "dark · light · satellite imagery"),
            ("Boundaries", "State · Districts · Taluks · SHO regions"),
            ("Jurisdiction", "seat scope applied server-side"),
            ("Crime filters", "property · body · cyber · women · traffic · drugs"),
            ("Time window", "anchored to the latest data date"),
            ("Time of day", "5 buckets"),
            ("Severity", "gravity of offence"),
            ("Forecast horizon", "7 · 14 · 30 days")]
    for i, (t, b) in enumerate(ctrl):
        s.text(44, 116 + i * 47, t, size=10, weight="700")
        s.wrap(44, 130 + i * 47, b, size=8.6, fill=DIM, width_chars=30)
        s.rect(44, 136 + i * 47, 186, 8, fill=WHITE, stroke=RULE, r=4)

    s.rect(256, 90, 1020, 400, fill="#F8FAFC", stroke=RULE, r=6)
    s.path("M300 130 L520 112 L640 190 L604 300 L430 350 L306 268 Z",
           stroke=DIM, sw=1.3, fill="#EEF2FF", arrow=False)
    s.path("M640 190 L860 150 L960 250 L880 360 L604 300 Z", stroke=DIM,
           sw=1.3, fill="#F3F4F6", arrow=False)
    s.path("M860 150 L1120 130 L1200 260 L960 250 Z", stroke=DIM, sw=1.3,
           fill="#EEF2FF", arrow=False)
    s.text(360, 200, "District boundary", size=9.5, fill=DIM)
    for cx, cy, col in [(420, 210, PRIMARY), (462, 236, PRIMARY),
                        (700, 240, AMBER), (742, 214, AMBER),
                        (768, 268, AMBER), (1010, 200, TEAL),
                        (1064, 232, PRIMARY), (520, 300, PRIMARY)]:
        s.parts.append(f'<circle cx="{cx}" cy="{cy}" r="6.5" fill="{col}" '
                       f'fill-opacity="0.85" stroke="{WHITE}" '
                       f'stroke-width="1.4"/>')
    s.parts.append(f'<circle cx="736" cy="242" r="52" fill="{AMBER}" '
                   f'fill-opacity="0.16" stroke="{AMBER}" stroke-width="1.4" '
                   f'stroke-dasharray="5 4"/>')
    s.text(700, 316, "Hotspot · ST-DBSCAN + KDE", size=9, fill=AMBER,
           weight="700")
    for cx, cy in [(600, 170), (900, 300), (1150, 190)]:
        s.poly([(cx, cy - 7), (cx + 6, cy + 5), (cx - 6, cy + 5)], fill=INK,
               stroke=WHITE, sw=1)
    s.text(1112, 196, "station", size=8.6, fill=DIM)

    s.rect(430, 366, 306, 112, fill=WHITE, stroke=PRIMARY, sw=1.6, r=6)
    s.text(444, 388, "FIR 100239 · Motorcycle theft", size=11, weight="700")
    s.text(444, 404, "Gravity: Serious   Status: Under investigation", size=9.2,
           fill=DIM)
    s.text(444, 418, "Station: Jayanagar   Registered: 14 Mar 2025", size=9.2,
           fill=DIM)
    s.text(444, 432, "Section: BNS 303(2)", size=9.2, fill=DIM)
    s.pill(444, 442, 122, 24, "Open case file", fill="#DBEAFE",
           stroke=PRIMARY, colour=PRIMARY)
    s.pill(574, 442, 122, 24, "Send to board", colour=DIM)

    s.rect(30, 496, 1246, 26, fill=SURFACE, stroke=RULE, r=5)
    leg = [("property", PRIMARY), ("body", "#DC2626"), ("cyber", INDIGO),
           ("women", "#DB2777"), ("traffic", AMBER), ("drugs", TEAL),
           ("hotspot", AMBER), ("police station", INK)]
    for i, (t, c) in enumerate(leg):
        x = 44 + i * 152
        s.parts.append(f'<circle cx="{x}" cy="509" r="5" fill="{c}"/>')
        s.text(x + 12, 513, t, size=9, fill=DIM)
    s.save(out / "wire-03-map-hotspots.svg")


def wire_board(out: Path):
    s = Svg(1300, 540, "Wireframe — Investigation Board")
    _wf_frame(s, "Wireframe · Investigation Board",
              "Objects stay LINKED to governed sources; the pinned snapshot "
              "preserves exactly what the investigator saw. 36 endpoints "
              "including branch, diff, promote-edge and search-around.")

    s.rect(24, 50, 190, 440, fill=SURFACE, stroke=RULE, r=6)
    s.text(38, 72, "Palette & filters", size=10.5, weight="700")
    for i, t in enumerate(["Object types", "Evidence vs hypothesis",
                           "Hide by kind", "Text search", "Pin object",
                           "Add sticky note", "Add frame", "Add text",
                           "Path finder", "Search around", "Time scrubber",
                           "Focus mode"]):
        s.rect(38, 84 + i * 33, 162, 25, fill=WHITE, stroke=RULE, r=4)
        s.text(48, 101 + i * 33, t, size=9.4, fill=DIM)

    s.rect(226, 50, 796, 400, fill="#FCFCFD", stroke=RULE, r=6)
    for gx in range(266, 1010, 40):
        s.line(gx, 58, gx, 442, stroke="#EEF0F3", sw=0.8, arrow=False)
    for gy in range(90, 445, 40):
        s.line(234, gy, 1014, gy, stroke="#EEF0F3", sw=0.8, arrow=False)

    s.rect(560, 236, 366, 196, fill="#EEF2FF", stroke=INDIGO, sw=1.4, r=8,
           dash="6 4")
    s.text(574, 258, "INVESTIGATION FRAME · vehicle disposal chain", size=9.6,
           weight="700", fill=INDIGO)

    nodes = [("Case 100239", "CaseMaster", 268, 88, PRIMARY),
             ("Complainant", "CasePartyRole", 268, 186, TEAL),
             ("Accused A", "Accused", 452, 88, AMBER),
             ("Phone +91…", "Device", 452, 186, DIM),
             ("Vehicle KA-01", "PropertyItem", 596, 288, AMBER),
             ("Buyer", "CanonicalPerson", 760, 288, AMBER),
             ("Account", "FinancialAccount", 760, 366, DIM)]
    for label, kind, x, y, col in nodes:
        s.rect(x, y, 150, 56, fill=WHITE, stroke=col, sw=1.5, r=6)
        s.text(x + 11, y + 22, label, size=10.4, weight="700")
        s.text(x + 11, y + 38, kind, size=8.6, fill=DIM, font=MONO)
    s.line(343, 144, 343, 184, stroke=TEAL, sw=1.6, marker="arrowT")
    s.line(418, 116, 450, 116, stroke=PRIMARY, sw=1.8, marker="arrowP")
    s.text(360, 108, "verified", size=8.4, fill=PRIMARY, weight="700")
    s.line(527, 144, 527, 184, stroke=DIM, sw=1.5)
    s.path("M527 242 L527 316 L594 316", stroke=AMBER, sw=1.7, marker="arrowA")
    s.line(746, 316, 758, 316, stroke=AMBER, sw=1.7, marker="arrowA")
    s.path("M835 344 L835 394 L758 394", stroke=DIM, sw=1.5, dash="4 3")
    s.text(600, 424, "hypothesis link (dashed) — not evidence", size=8.6,
           fill=DIM, italic=True)

    s.rect(268, 300, 150, 92, fill="#FEF9C3", stroke="#D9C24A", sw=1.2, r=5)
    s.text(280, 320, "Sticky note", size=9.6, weight="700", fill="#713F12")
    s.wrap(280, 336, "Same phone appears in 3 other FIRs — check CDR import "
                     "before charging.", size=8.4, fill="#713F12",
           width_chars=24)

    s.rect(1034, 50, 242, 400, fill=SURFACE, stroke=RULE, r=6)
    s.text(1048, 72, "Source inspector", size=10.5, weight="700")
    insp = [("Properties", "typed fields from the governed record"),
            ("Pinned snapshot", "what the investigator saw, with version id"),
            ("Live reference", "still linked to the source of truth"),
            ("Related records", "expand without detaching"),
            ("Provenance", "source system, version, content hash"),
            ("Activity", "who changed what, when")]
    for i, (t, b) in enumerate(insp):
        y = 84 + i * 60
        s.rect(1048, y, 214, 52, fill=WHITE, stroke=RULE, r=5)
        s.text(1058, y + 18, t, size=9.8, weight="700")
        s.wrap(1058, y + 32, b, size=8.4, fill=DIM, width_chars=34)

    s.rect(226, 458, 1050, 32, fill=SURFACE, stroke=RULE, r=5)
    for i, t in enumerate(["Canvas", "Timeline", "Evidence trail", "Table",
                           "History", "Diffs", "Statistics", "Branch",
                           "Share / lock", "Export"]):
        act = i == 0
        s.pill(238 + i * 104, 464, 96, 20, t,
               fill="#DBEAFE" if act else WHITE,
               stroke=PRIMARY if act else RULE,
               colour=PRIMARY if act else DIM, size=8.8)
    s.save(out / "wire-04-investigation-board.svg")


def wire_case_ask(out: Path):
    s = Svg(1300, 540, "Wireframe — Case File and Ask DRISHTI")
    _wf_frame(s, "Wireframe · Case File (18 sub-pages) and Ask DRISHTI",
              "Left: the complete governed record. Right: natural language that "
              "never becomes arbitrary SQL — a constrained plan, a read-only "
              "guard, then citations.")
    s.line(650, 46, 650, 494, stroke=RULE, sw=1.4, arrow=False)

    s.text(28, 68, "FIR 100239 · Motorcycle theft · Jayanagar", size=11.5,
           weight="700")
    s.caption(28, 84, "Under investigation · registered 14 Mar 2025 · "
                      "BNS 303(2)", size=9.2)
    subs = ["Overview", "Timeline", "Complainant", "Victims", "Accused",
            "Acts & sections", "Arrests", "Chargesheet", "Evidence",
            "Statements", "Property & seizures", "Digital & financial",
            "Court & lifecycle", "Network", "Similar cases", "AI summary",
            "Leads", "Investigation assistant"]
    for i, t in enumerate(subs):
        y = 98 + i * 21
        act = i == 0
        if act:
            s.rect(26, y - 11, 182, 19, fill="#DBEAFE", stroke="none", sw=0,
                   r=4)
        s.text(36, y + 2, t, size=9.2, fill=PRIMARY if act else DIM,
               weight="700" if act else "400")
    s.rect(218, 96, 408, 380, fill=WHITE, stroke=RULE, r=6)
    s.text(232, 116, "Overview", size=10.8, weight="700")
    for i, (t, b) in enumerate([
            ("Core facts", "crime number, category, gravity, station, "
                            "jurisdiction, occurrence window"),
            ("Parties", "complainant, victims, accused with typed roles"),
            ("Legal", "acts and sections, arrests, chargesheet readiness"),
            ("Evidence", "objects with hash, size, MIME, version, custody trail"),
            ("Geography", "location, boundary containment, nearby hotspots"),
            ("Lifecycle", "append-only case events and court schedule")]):
        y = 130 + i * 57
        s.rect(232, y, 380, 49, fill=SURFACE, stroke=RULE, r=5)
        s.text(244, y + 18, t, size=9.8, weight="700")
        s.wrap(244, y + 32, b, size=8.4, fill=DIM, width_chars=62)
    s.pill(232, 444, 148, 24, "Send to Board", fill="#DBEAFE", stroke=PRIMARY,
           colour=PRIMARY)
    s.caption(392, 461, "expands 14 nodes / 13 verified links", size=8.8)

    s.text(676, 68, "Ask DRISHTI", size=11.5, weight="700")
    for i, t in enumerate(["Chat", "History", "Saved queries"]):
        s.pill(676 + i * 108, 78, 100, 22, t,
               fill="#DBEAFE" if i == 0 else SURFACE,
               stroke=PRIMARY if i == 0 else RULE,
               colour=PRIMARY if i == 0 else DIM, size=9)
    s.rect(676, 110, 600, 40, fill=SURFACE, stroke=RULE, r=6)
    s.text(690, 135, "“Which districts in my range had the sharpest rise in "
                     "vehicle theft last quarter?”", size=9.6, fill=INK)
    steps = [
        ("1 · Plan", "Bedrock GLM-4.7-Flash behind the signed adapter, or a "
                     "LABELLED deterministic fallback — never a silent switch"),
        ("2 · Validate", "Schema-reference check catches a hallucinated column; "
                         "exactly one bounded repair attempt"),
        ("3 · Guard", "Single statement, must start SELECT/WITH, ~50 forbidden "
                      "keywords, ~25 forbidden functions, enforced row cap"),
        ("4 · Execute", "drishti_readonly role inside a read-only transaction — "
                        "four independent layers, not one"),
        ("5 · Ground", "Reply composed only from returned rows; citations from "
                       "result-set ids; SHA-256 of the executed SQL recorded"),
    ]
    for i, (t, b) in enumerate(steps):
        y = 160 + i * 50
        s.rect(676, y, 600, 42, fill=WHITE, stroke=RULE, r=5)
        s.text(690, y + 17, t, size=9.8, weight="700", fill=PRIMARY)
        s.wrap(756, y + 17, b, size=8.6, fill=DIM, width_chars=76)
    s.rect(676, 416, 600, 60, fill="#EFF6FF", stroke=PRIMARY, r=6)
    s.text(690, 436, "Answer · confidence 0.82 · 4 citations", size=10,
           weight="700", fill=PRIMARY)
    s.wrap(690, 452, "Sources: CaseMaster:100239 · District:20 · "
                     "CrimeHotspot:14 · executed SQL shown in full. Voice below "
                     "the confidence threshold requires confirmation.",
           size=8.6, fill=DIM, width_chars=88)
    s.save(out / "wire-05-case-file-and-ask.svg")


# =========================================================================== #
# 3. PROCESS FLOWS
# =========================================================================== #
def flow_operational(out: Path):
    s = Svg(1840, 760, "DRISHTI end-to-end operational process")
    head(s, "End-to-end operational process",
         "Five question paths converge on ONE human-review gate, and all three "
         "decision outcomes are recorded — including rejection.")

    ingest = [
        ("Complaint · FIR · import · live event",
         "Guided 7-step intake, scanned-FIR OCR that only PRE-FILLS a draft, "
         "template imports, CCTV and hazard feeds"),
        ("Validate schema, quality and jurisdiction",
         "Failures become reviewable DataQualityIssues; nothing is silently "
         "repaired"),
        ("Create or update governed objects",
         "Typed case, party role, evidence, property, transaction, statement, "
         "lifecycle event"),
        ("Resolve people, places, devices, accounts",
         "Entity-resolution candidates are PROPOSALS — nothing is ever "
         "auto-merged"),
        ("Build verified relationships + snapshots",
         "Immutable feature snapshot binds every later prediction to its inputs"),
    ]
    for i, (t, b) in enumerate(ingest):
        x = 28 + i * 362
        s.box(x, 90, 342, 92, t, b, fill=SURFACE, accent=PRIMARY, tsize=11.8,
              bsize=9.4)
        if i < 4:
            s.line(x + 346, 136, x + 358, 136, stroke=PRIMARY, sw=1.8,
                   marker="arrowP")

    s.diamond(920, 226, 260, 58, "Operational question", stroke=PRIMARY)
    s.line(920, 186, 920, 198, stroke=PRIMARY, sw=1.8, marker="arrowP")

    paths = [
        ("Case", "Case file and lifecycle", "18 governed sub-pages", PRIMARY),
        ("Relationship", "Network analysis · Investigation Board",
         "communities, hidden links, money trail, paths", INDIGO),
        ("Location", "Map, hotspots and patrol planning",
         "5 modes · 19 deck.gl layers", TEAL),
        ("Trend", "Analytics, forecast and backtest",
         "5 inspectable model layers", AMBER),
        ("Natural language", "Ask DRISHTI scoped planner",
         "read-only guarded SQL with citations", PRIMARY),
    ]
    for i, (tag, t, b, col) in enumerate(paths):
        x = 28 + i * 362
        s.box(x, 306, 342, 82, t, b, fill=WHITE, accent=col, tsize=11.5,
              bsize=9.4)
        s.pill(x, 286, 122, 20, tag, fill=WHITE, stroke=col, colour=col,
               size=8.8)
        mid = x + 171
        s.path(f"M920 256 L920 274 L{mid} 274 L{mid} 300", stroke=col, sw=1.6,
               arrow=True, marker="arrowP" if col == PRIMARY else "arrow")

    s.box(28, 424, 1784, 62, "Human review",
          "Every path lands here. The reviewer sees the evidence, the model "
          "version, the confidence, the time window and the provenance — never "
          "a bare score. Aggregate-only seats never see case-level rows.",
          fill="#EEF2FF", accent=INDIGO, tsize=13, bsize=10)
    for i in range(5):
        x = 28 + i * 362 + 171
        s.line(x, 392, x, 420, stroke=DIM, sw=1.5)

    s.diamond(920, 528, 240, 54, "Officer decision", stroke=INDIGO)
    s.line(920, 490, 920, 500, stroke=INDIGO, sw=1.8, marker="arrowP")

    outs = [("Approve or act", "Controlled operational action — a person "
                               "authorises it, not a model", TEAL),
            ("Modify", "Record the rationale and the revised plan", AMBER),
            ("Reject", "Record the rejection and the feedback, which feeds "
                       "model monitoring", AMBER)]
    for i, (t, b, col) in enumerate(outs):
        x = 240 + i * 480
        s.box(x, 592, 440, 66, t, b, fill=WHITE, accent=col, tsize=11.8,
              bsize=9.4)
        s.path(f"M920 556 L920 574 L{x + 220} 574 L{x + 220} 588",
               stroke=col, sw=1.6, marker="arrowT" if col == TEAL else "arrowA")

    s.box(28, 676, 1784, 54, "Append-only audit and evidence trail",
          "Audit rows are written transactionally with the action, so a "
          "rolled-back action rolls back its audit. Sensitive fields are "
          "stripped before storage. Nothing in this chain auto-dispatches, "
          "auto-accuses or closes a case.",
          fill=SURFACE, accent=INDIGO, tsize=12.5, bsize=9.8)
    for i in range(3):
        x = 240 + i * 480 + 220
        s.line(x, 662, x, 672, stroke=DIM, sw=1.5)
    s.save(out / "flow-01-operational-process.svg")


def flow_usecase(out: Path):
    s = Svg(1840, 760, "DRISHTI use-case diagram")
    head(s, "Use-case diagram — actors, surfaces and scope",
         "Role selects the surface; seat scope selects the data. Aggregate-only "
         "seats are deliberately denied the six case-level destinations.")

    # Actor codes instead of connector lines: with 5 actors x 14 capabilities,
    # drawn links become unreadable spaghetti. A badge matrix says the same
    # thing and stays legible when the slide is projected.
    actors = [
        ("S", "State / Senior Command", "DGP state · ADGP wing · DIG range",
         "Aggregate only above district", PRIMARY),
        ("D", "District Command & SHO", "SP · CP · station chief",
         "Reads and writes within jurisdiction", PRIMARY),
        ("I", "Investigating Officer", "PSI · ASI · HC · PC",
         "Assigned cases, own station", TEAL),
        ("E", "Emergency & Traffic", "response and traffic wings",
         "Hazards, resources, dispatch review", INDIGO),
        ("A", "System & Model Admin", "platform scope",
         "Seats, roles, registry, audit", AMBER),
    ]
    s.kicker(28, 92, "Actors")
    for i, (code, t, sub, note, col) in enumerate(actors):
        y = 104 + i * 108
        s.rect(28, y, 340, 96, fill=SURFACE, stroke=RULE, r=6)
        s.parts.append(f'<path d="M31 {y + 2} L31 {y + 94}" stroke="{col}" '
                       f'stroke-width="3.4" stroke-linecap="round"/>')
        s.parts.append(f'<circle cx="{28 + 30}" cy="{y + 26}" r="14" '
                       f'fill="{col}"/>')
        s.text(58, y + 31, code, size=13, weight="700", fill=WHITE,
               anchor="middle")
        s.wrap(80, y + 24, t, size=12, weight="700", width_chars=32)
        s.wrap(46, y + 56, sub, size=9.4, fill=DIM, width_chars=52)
        s.wrap(46, y + 74, note, size=9.4, fill=col, weight="600",
               width_chars=52)

    caps = [
        ("Command Center", "role-adaptive KPI board", "S D I", PRIMARY),
        ("Case Explorer & Case File", "18 governed sub-pages", "D I", PRIMARY),
        ("Intake & review queues", "wizard, OCR pre-fill, imports, quality",
         "D I", PRIMARY),
        ("People, Entities & Face", "canonical profiles, reviewable matches",
         "D I", TEAL),
        ("Network Analysis", "communities, hidden links, money, paths",
         "S* D I", INDIGO),
        ("Investigation Board", "36 endpoints, snapshots, evidence trail",
         "S* D I", INDIGO),
        ("Map, Hotspots & Patrol", "5 modes, boundary layers, forecasts",
         "S D I E", TEAL),
        ("Live Watch Wall", "propose → confirm → dispatch, each confirmed",
         "D E", AMBER),
        ("Analytics & Forecasting", "6 modes, backtests, explainability",
         "S D E", AMBER),
        ("Ask DRISHTI", "cited answers, voice, saved queries", "S D I E A",
         PRIMARY),
        ("Emergency Response", "situation, live, forecast, resources, plans",
         "E", INDIGO),
        ("Outcomes", "conviction rate, disposal mix — counts only", "S D",
         TEAL),
        ("Governance Registry", "models, snapshots, predictions, labels",
         "S A", INDIGO),
        ("Admin Console", "15 tabs: seats, roles, UI visibility, audit", "A",
         AMBER),
    ]
    s.kicker(404, 92, "Capabilities, and which actors reach them")
    codes = {a[0]: a[4] for a in actors}
    for i, (t, b, who, col) in enumerate(caps):
        x = 404 + (i % 2) * 712
        y = 104 + (i // 2) * 82
        s.rect(x, y, 692, 70, fill=WHITE, stroke=RULE, r=6)
        s.parts.append(f'<path d="M{x + 3} {y + 2} L{x + 3} {y + 68}" '
                       f'stroke="{col}" stroke-width="3.4" '
                       f'stroke-linecap="round"/>')
        s.wrap(x + 14, y + 22, t, size=11.8, weight="700", width_chars=40)
        s.wrap(x + 14, y + 40, b, size=9.4, fill=DIM, width_chars=68)
        badges = who.split()
        for j, cd in enumerate(badges):
            bx = x + 692 - 18 - (len(badges) - j) * 32
            col2 = codes[cd[0]]
            s.parts.append(f'<circle cx="{bx}" cy="{y + 35}" r="12.5" '
                           f'fill="{col2}" fill-opacity="0.14" '
                           f'stroke="{col2}" stroke-width="1.3"/>')
            s.text(bx, y + 40, cd, size=10.5 if "*" in cd else 11,
                   weight="700", fill=col2, anchor="middle")

    s.box(28, 680, 1784, 46,
          "Aggregate-only seats are denied the six case-level destinations",
          "State- and wing-scoped seats (DGP, ADGP wing) never reach Cases, "
          "Intake, People & Entities, Face Recognition, Network Analysis or the "
          "Investigation Board. This mirrors the server's require_case_level "
          "guard: the affordance is REMOVED rather than offered and then refused 403.",
          fill="#FFFBEB", accent=AMBER, tsize=11.8, bsize=9.6)
    s.caption(28, 744, "S* = range-scoped Senior Command (DIG) only. An "
                       "ADGP wing seat is state-wide but aggregate-only, so it "
                       "shares the role and not the case-level access — which "
                       "is exactly why role and scope are separate axes.",
              size=9.6)
    s.save(out / "flow-02-use-case.svg")


def flow_send_to_board(out: Path):
    s = Svg(1840, 762, "Send to Board — governed expansion sequence")
    head(s, "“Send to Board” — governed case-network expansion",
         "A concrete, verifiable governance story: for case 100239 this returns "
         "14 nodes and 13 verified links, and appends its own audit events.")

    lanes = [("Officer", PRIMARY, 120), ("Case File (UI)", PRIMARY, 380),
             ("Board service (AppSail)", TEAL, 640),
             ("Governed data stores", AMBER, 900),
             ("Investigation Board", INDIGO, 1160),
             ("Evidence trail", INDIGO, 1420)]
    for name, col, x in lanes:
        s.rect(x - 96, 84, 192, 40, fill=SURFACE, stroke=col, r=6)
        s.wrap(x, 100, name, size=10.8, weight="700", anchor="middle",
               width_chars=24)
        s.line(x, 126, x, 640, stroke=RULE, sw=1.2, dash="4 4", arrow=False)

    msgs = [
        (0, 1, "Open case 100239", 160, PRIMARY),
        (0, 1, "Select “Send to Board”", 200, PRIMARY),
        (1, 2, "Request governed case-network expansion", 240, PRIMARY),
        (2, 3, "Load case, parties, evidence, property, legal, lifecycle", 280,
         AMBER),
        (3, 2, "Typed objects + verified relationships + source versions", 320,
         AMBER),
        (2, 1, "Preview: 14 nodes, 13 verified links", 360, TEAL),
        (0, 1, "Confirm — create board and pin", 400, PRIMARY),
        (1, 2, "Persist objects, links and pinned snapshots", 440, PRIMARY),
        (2, 5, "Append board-creation and pin events", 480, INDIGO),
        (2, 4, "Board id + hydrated graph", 520, TEAL),
        (4, 0, "Interactive canvas, inspector, provenance", 560, INDIGO),
    ]
    for a, b, label, y, col in msgs:
        x1, x2 = lanes[a][2], lanes[b][2]
        back = x2 < x1
        mk = {PRIMARY: "arrowP", TEAL: "arrowT", AMBER: "arrowA",
              INDIGO: "arrowP"}[col]
        s.line(x1 + (-8 if back else 8), y, x2 + (8 if back else -8), y,
               stroke=col, sw=1.6, dash="5 3" if back else None, marker=mk)
        # width_chars is generous on purpose: a wrapped second line would land
        # on the arrow itself.
        s.wrap((x1 + x2) / 2, y - 9, label, size=9.4,
               fill=col if not back else DIM, weight="600", anchor="middle",
               width_chars=74)

    s.box(28, 676, 580, 58, "Live reference, not a copy",
          "Every pinned object stays linked to its source of truth, so the "
          "board can never drift into a private, unverifiable version of the case.",
          fill=SURFACE, accent=TEAL, tsize=11, bsize=9.2)
    s.box(628, 676, 580, 58, "Pinned snapshot, not a screenshot",
          "The snapshot preserves what the investigator saw, with its version "
          "id — so a later change to the record is visible as a diff.",
          fill=SURFACE, accent=INDIGO, tsize=11, bsize=9.2)
    s.box(1228, 676, 584, 58, "Evidence separated from hypothesis",
          "Verified links render solid; hypothesis links render dashed and are "
          "filterable. A graph relationship never establishes guilt.",
          fill=SURFACE, accent=AMBER, tsize=11, bsize=9.2)
    s.save(out / "flow-03-send-to-board.svg")


def flow_governance(out: Path):
    s = Svg(1840, 700, "DRISHTI model governance lifecycle")
    head(s, "Model governance lifecycle — why a forecast is evidence",
         "No model reaches an operational surface without a backtest, a "
         "registered version, a recorded human disposition and a monitoring "
         "loop back to the start.")

    ring = [
        ("Validated synthetic data", "quality and jurisdiction rules passed",
         PRIMARY),
        ("Immutable feature snapshot", "id, source cutoff, feature schema "
                                       "version", PRIMARY),
        ("Train / configure candidate", "TabFM · TimesFM · ST-GNN · "
                                        "near-repeat · KDE", INDIGO),
        ("Temporal + geographic backtest", "leakage-safe rolling origin; "
                                           "6 origins × 32 districts", INDIGO),
        ("Model review and approval", "a named human, not an automatic "
                                      "promotion", AMBER),
        ("Versioned model registry", "ModelVersion, benchmarks, training "
                                     "snapshot", AMBER),
        ("Scoped inference", "jurisdiction and purpose applied before the "
                             "model runs", TEAL),
        ("Confidence, drivers, provenance", "surfaced in the UI beside the "
                                            "number", TEAL),
    ]
    for i, (t, b, col) in enumerate(ring):
        x, y = 28 + (i % 4) * 456, 92 + (i // 4) * 132
        s.box(x, y, 424, 108, f"{i + 1}. {t}", b, fill=WHITE, accent=col,
              tsize=12, bsize=9.6)
        if i % 4 < 3:
            s.line(x + 428, y + 54, x + 450, y + 54, stroke=col, sw=1.8,
                   marker="arrowP" if col == PRIMARY else "arrow")
    # Wrap from step 4 down to step 5, routed in the 24 px gutter between rows
    # so it cannot cross a card.
    s.path("M1608 200 L1608 212 L16 212 L16 278 L24 278", stroke=INDIGO,
           sw=1.6, marker="arrowP")

    s.box(28, 356, 880, 76, "9. Human accept / modify / reject",
          "Mandatory. The disposition is recorded against the prediction id, so "
          "'who acted on this and why' is answerable months later. No model "
          "output becomes a coercive action.",
          fill="#EEF2FF", accent=INDIGO, tsize=12.5, bsize=9.8)
    s.box(932, 356, 880, 76, "10. Drift, feedback and performance monitoring",
          "Accepted, modified and rejected outcomes feed back into the next "
          "backtest. A layer that degrades is excluded from fusion, and the "
          "exclusion reason is recorded.",
          fill="#EEF2FF", accent=INDIGO, tsize=12.5, bsize=9.8)
    s.line(912, 394, 928, 394, stroke=INDIGO, sw=1.8, marker="arrowP")
    s.path("M1372 432 L1372 452 L470 452 L470 440", stroke=INDIGO, sw=1.5,
           dash="5 4", marker="arrowP")
    s.text(880, 468, "monitoring reopens the backtest — the loop never closes "
                     "permanently", size=9.6, fill=INDIGO, italic=True,
           anchor="middle")

    s.text(28, 508, "The two rules that make this more than a diagram",
           size=13, weight="700", fill=INK)
    s.box(28, 522, 880, 82, "Fails closed, never degrades silently",
          "A requested TabFM job that cannot run on CUDA with a verified weight "
          "digest returns CUDA_UNAVAILABLE. A CPU statistical model can never be "
          "returned labelled as a foundation model. Every result carries "
          "actual_backend, actual_device and model_artifact_digest, HMAC-signed "
          "so AppSail can verify it.",
          fill="#FFFBEB", accent=AMBER, tsize=12, bsize=9.6)
    s.box(932, 522, 880, 82, "Refuses to promote a weaker model",
          "The current in-context fallback scores 0.4141 accuracy against a "
          "0.6484 prior-period baseline on an identical time-based split, so the "
          "registry does NOT mark it active. Fusion also refuses any layer whose "
          "output lacks the current analytics-policy attestation.",
          fill="#FFFBEB", accent=AMBER, tsize=12, bsize=9.6)

    s.box(28, 616, 1784, 62, "Every governed prediction carries a reproducible envelope",
          "prediction_id · model_id · model_version · feature_snapshot_id · "
          "jurisdiction · as_of · horizon · confidence · explanation · "
          "source_hash · review_status (pending | accepted | modified | rejected)",
          fill=SURFACE, accent=PRIMARY, tsize=12, bsize=10)
    s.save(out / "flow-04-model-governance.svg")


# =========================================================================== #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/assets/diagrams")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print("architecture:")
    arch_system(out)
    arch_request(out)
    arch_data(out)
    print("wireframes:")
    wire_login(out)
    wire_shell(out)
    wire_map(out)
    wire_board(out)
    wire_case_ask(out)
    print("process flows:")
    flow_operational(out)
    flow_usecase(out)
    flow_send_to_board(out)
    flow_governance(out)
    print(f"\n12 diagrams in {out.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
