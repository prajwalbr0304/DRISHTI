# DRISHTI submission diagrams

Twelve diagrams for the KSP Datathon 2026 prototype deck: three architecture,
five wireframe, four process-flow. Every figure and label is drawn from the
codebase, not from the (partly stale) repository README — see
`KSP-Datathon-2026-PPT-Agent-Brief.md` §6.1 for the divergences.

## Regenerating

```powershell
python scripts/generate_diagrams.py                       # SVG source
powershell -ExecutionPolicy Bypass -File scripts/rasterise_diagrams.ps1   # PNG at 2x
```

The generator has no third-party dependencies. Rasterising uses the Playwright
Chromium already installed for `web/` end-to-end tests, because `python-pptx`
cannot embed SVG — PowerPoint needs the bitmaps in `png/`.

Edit `scripts/generate_diagrams.py` and re-run both commands; never hand-edit
the SVG or PNG output.

## Slide mapping

| File | Slide | Aspect | Notes |
|---|---|---|---|
| `arch-01-system.svg` | **7** — Architecture diagram | 1840×950 (1.94:1) | The primary architecture figure. Four zones plus a governance strip and four trust-boundary cards. Tall for a 9.10 in placement — allow ~4.7 in of height, or crop the trust-boundary strip onto slide 7B. |
| `arch-02-request-lifecycle.svg` | **7B** — Architecture detail | 1840×596 (3.09:1) | Ten numbered steps in a 5×2 grid, colour-coded by tier, plus a "what cannot happen" strip. Wide and shallow: fits the 9.10 × 3.68 in content zone almost exactly. |
| `arch-03-data.svg` | **7C** or appendix | 1840×700 (2.63:1) | One ontology, two serving planes. Good companion to the database-inventory numbers on slide 12. |
| `wire-01-login.svg` | **6** — Wireframes | 1300×540 (2.41:1) | Role-scoped sign-in. Carries the role-vs-scope argument. |
| `wire-02-app-shell.svg` | **6** | 1300×540 | Application shell: sidebar, top bar, role-adaptive body, peek rail. |
| `wire-03-map-hotspots.svg` | **6** | 1300×540 | Map & Hotspots with the incident popup that opens a case file. |
| `wire-04-investigation-board.svg` | **6** | 1300×540 | Investigation Board: verified vs hypothesis links, frame, source inspector. |
| `wire-05-case-file-and-ask.svg` | **6B** (optional) | 1300×540 | Case File's 18 sub-pages beside the five-stage Ask DRISHTI guard chain. |
| `flow-01-operational-process.svg` | **5** — Process flow | 1840×760 (2.42:1) | The primary process figure: five question paths → one human-review gate → three recorded outcomes → append-only audit. |
| `flow-02-use-case.svg` | **5B** — Use-case diagram | 1840×760 | Actor-code badge matrix (S/D/I/E/A) rather than connector lines, which are unreadable at 14 capabilities × 5 actors. |
| `flow-03-send-to-board.svg` | **5C** or appendix | 1840×762 | Sequence diagram for governed case-network expansion. Concrete: 14 nodes, 13 verified links for case 100239. |
| `flow-04-model-governance.svg` | **14** or **15** | 1840×700 | Ten-stage governance lifecycle plus the two fail-closed rules and the reproducible prediction envelope. |

Four wireframes fit a 2×2 grid on slide 6 at 4.40 × 1.72 in each (aspect 2.56,
close enough to 2.41 that letterboxing is negligible).

## Placement snippet

```python
add_image_fit(slide, "docs/assets/diagrams/png/arch-01-system.png",
              left=0.45, top=1.72, box_w=9.10, box_h=3.66,
              alt="DRISHTI solution architecture: browser to Zoho Catalyst "
                  "Slate, Authentication, API Gateway, a gateway_api function "
                  "minting a signed context, AppSail FastAPI, Catalyst "
                  "operational services, and a protected server-to-server AWS "
                  "analytical plane.")
```

`add_image_fit` is in `KSP-Datathon-2026-PPT-Agent-Brief.md` §7.5. Always pass
alt text; the brief's post-build audit checks for it.

## Design tokens

Mirrors §2.1 of the brief so the diagrams and the deck match:
Ink `#111827` · Dim `#4B5563` · Rule `#D1D5DB` · Surface `#F3F4F6` ·
Primary `#0B6CFB` · Teal `#0E9F8C` · Amber `#B45309` · Indigo `#4338CA`.

Amber consistently marks a limitation, a fail-closed path or the protected AWS
plane. Teal marks a verified or server-side path. Indigo marks governance and
the Emergency Response workspace.

---

All records depicted are synthetic demonstration data. Predictions are decision
support; a human officer decides.
