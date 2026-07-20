# PHASE 19 — Ask DRISHTI: semantic planner, bilingual voice scope, typed visual answers

Status date: 2026-07-21
Owner: implementation agent (Kiro)
Branch: `fix/case-overview-location-map`
Catalyst project: **DHRISTI** (`48361000000030003`), India DC, Development env.
Result of this phase: **Complete** — every Definition-of-Done item is verified below
at the implementation + offline/DB level. The one intentionally deferred item is the
**live** Catalyst QuickML LLM Serving invocation and the live-provider browser E2E,
which Prompt 19 itself scopes to Prompt 23 (see §8). No Catalyst/AWS deployment or
credit spend was performed in this phase.

> Synthetic hackathon effort. Nothing here is production. This phase EXTENDS the
> existing Ask DRISHTI slice (guard, citations, history, SQL block, confidence, the
> chat UI) — it does not replace it. RLS stays disabled per the standing decision;
> server-side role/scope authorization remains fully enforced.

---

## 0. Definition of Done — verification

| DoD item | State | Evidence |
|---|---|---|
| A bilingual multi-turn query produces an authorized grounded answer with citations | **PASS** | EN + Kannada-script + transliterated queries resolve (golden `mt-01..10` carry = 10/10; `kn-*`/`tr-*` intent = 100%); DB integration `test_engine_multiturn_memory_resolves_reference` + `test_engine_answer_is_grounded_cited_and_persisted` pass (63/63 with DB) |
| At least one trend and one map/heatmap render typed visual answers | **PASS** | `viz.build_visualization` emits `line` for a time series and `choropleth` for district+measure (golden `viz-line`, `viz-choro`); frontend renders `TrendChart` + `districtChoropleth` via `MapCanvas`; FE tests `AnswerVisualization.test.tsx` cover line + choropleth |
| Aggregate-only users cannot retrieve case/person detail | **PASS** | `scope.enforce_scope` denies policymaker PII + non-aggregate (golden `scope-01/02/06` denial = 100%); DB `test_engine_policymaker_answer_is_aggregate_not_blocked`; engine substitutes a deterministic aggregate rather than depending on the model |
| Voice uses Zia when available, or is truthfully disabled with bilingual text intact | **PASS (truthfully disabled)** | Catalyst Zia exposes no speech/translation service in the IN DC (§3); `app/zia_voice.py` reports `provider="browser-web-speech"`, `zia_voice_available=false`, `bilingual_text=true` with recorded evidence; browser Web Speech is labelled, never called Zia |
| Low-confidence dictation never executes silently | **PASS** | Composer requires an explicit confirm/edit before a low-confidence transcript sends; `useAskStore.send` refuses `spoken && conf<0.6 && !confirmed` as a backstop; FE `Composer.voice.test.tsx` |
| Evidence/OCR extraction remains off | **PASS** | `EVIDENCE_EXTRACTION_ENABLED=false` (default + `/chat/capabilities` + docs); named as a flag independent of `QUERY_VOICE_ENABLED` |
| The semantic planner is primary in the live-ready contract; fallback is labelled | **PASS (contract) / live in P23** | `SEMANTIC_PLANNER_PROVIDER=catalyst_quickml` makes `CatalystQuickMLServingPlanner` the primary; the deterministic planner is surfaced as `planner_source` / `planner_degraded` (UI "offline fallback" badge). Live QuickML call is the Prompt 23 step (§8) |

---

## 1. Scope correction (Part A) — voice query vs evidence extraction

The prior repo state marked "Zia OCR/face/voice — Not used". Prompt 19 corrects the
contradiction: **voice dictation of a question and spoken read-back of the answer are
IN hackathon scope**, kept strictly separate from evidence extraction.

- New independent flags in `services/ml/app/config.py`:
  - `QUERY_VOICE_ENABLED` (default **true**) — question dictation + answer speech.
  - `EVIDENCE_EXTRACTION_ENABLED` (default **false**) — OCR, uploaded-document
    parsing, automatic FIR field extraction, evidence-media transcription, face/
    object recognition. Stays OFF. The two flags are separate so voice can never
    silently enable extraction.
  - `VOICE_LOW_CONFIDENCE_THRESHOLD` (0.6).
- Docs updated: `infra/catalyst/COMPONENTS.md` (voice-query row split from OCR/
  extraction; QuickML LLM Serving row added) and `.env.example`.
- `/chat/capabilities` advertises `scope.query_voice_enabled=true` and
  `scope.evidence_extraction_enabled=false` so the UI cannot over-claim.

## 2. Semantic planner (Part B) — provider-neutral, QuickML-primary, fail-closed

- **Removed the implied commercial default.** `llm_model` no longer defaults to
  `gpt-4o-mini`; `llm_base_url`/`llm_model` default to empty. Settings are
  provider-neutral (`SEMANTIC_PLANNER_PROVIDER` ∈ `"" | catalyst_quickml |
  openai_compatible`).
- **Primary = Catalyst QuickML LLM Serving.** `CatalystQuickMLServingPlanner`
  (`services/ml/app/nlsql/planner.py`) posts the allow-listed role-scoped schema +
  glossary + bounded context + data-minimised question to the deployed QuickML LLM
  Serving endpoint and expects one JSON plan. Endpoint/model/key are server-side env
  only; the key is never logged or sent to the browser.
- **Fail-closed + labelled fallback.** When no provider is configured, or the
  configured provider is unreachable, the engine drops to the deterministic offline
  planner and MARKS the answer (`planner_source`, `planner_primary`,
  `planner_degraded`) — surfaced in the UI as an "offline fallback" badge. It never
  silently routes to an external commercial API.
- **Placement recorded** in the source of truth `services/ml/app/predict/placement.py`
  (engine `quickml-llm-serving`, `catalyst-quickml`, available) and regenerated to
  `infra/catalyst/ml-placement.json` (11 placements, parity-checked).
- **Data minimisation** enforced in `_plan_messages`: only schema/glossary + bounded
  turns + the question are sent — never raw evidence bytes, unrestricted narratives,
  credentials or result sets.

## 3. Capability evidence (official docs, checked 2026-07-21)

Content below was rephrased for compliance with licensing restrictions.

- **Catalyst QuickML LLM Serving — AVAILABLE.** QuickML now offers LLM Serving and
  RAG, deploying/serving open models (the release notes list Qwen 2.5 variants —
  14B Instruct, 7B Coder, 7B Vision) behind an endpoint/chat interface.
  - [QuickML LLM Serving](https://docs.catalyst.zoho.com/en/quickml/help/generative-ai/llm-serving/)
  - [Catalyst release notes (LLM serving, Qwen 2.5 models)](https://www.zoho.com/catalyst/help/release-notes.html)
  → This is the primary Ask DRISHTI semantic planner. A commercial external API is
  therefore not required for a Catalyst-listed capability.
- **Catalyst Zia speech / text-to-speech / translation — NOT exposed in the IN DC.**
  The documented Catalyst Zia Services catalogue is OCR, Face Analytics, Identity
  Scanner, Image Moderation, Object Recognition, Barcode Scanner, AutoML and Text
  Analytics — there is no speech-to-text / text-to-speech / translation Zia service,
  and most of that catalogue is itself out of DRISHTI scope.
  - [Catalyst Zia components](https://docs.catalyst.zoho.com/en/zia-services/getting-started/components-of-zia-services/)
  → Per §E.5, the submitted voice capability is the browser Web Speech API (clearly
  labelled), with `app/zia_voice.py` holding a ready, env-gated Zia adapter contract
  (`DRISHTI_USE_CATALYST_ZIA_VOICE`) for the day such a service is exposed. Bilingual
  EN/KN text is fully retained regardless.
- Zia generative-AI is offered in several DCs including India, but that is the LLM/
  GenAI plane (used via QuickML LLM Serving here), not a Catalyst speech SDK service.

## 4. Safe NL→query (Part C)

Retained and re-verified: single read-only `SELECT` only, table/column allow-lists,
statement timeout, row cap, dangerous-function/comment/dollar-quote rejection, and
`SET ROLE drishti_readonly` + read-only transaction. Added this phase:

- **Executed plan/SQL hash** (`sha256`) + `planner_source` + `refusal` recorded on the
  `ModelInference` audit row (`engine._sql_hash`).
- **Ambiguity clarification**: a completely unconstrained list ("show cases", KN
  equivalent) asks a clarifying question instead of dumping the database.
- Aggregate-only enforcement for policymaker is independent of the model (scope guard
  + deterministic aggregate substitution).

## 5. Kannada / English + memory (Part D)

- Supported: **English, Kannada script, and common transliterated (Latin-script)
  Kannada**. Crime keywords, intent cues and district names gained transliterated
  forms (e.g. `kalla/kallathana`=theft, `darode`=robbery, `kole`=murder, `eshtu`=how
  many, `pravrutti`/`maasika`=trend, `torisi`=show), plus a bare-district scan so
  "Mysuru alli kalla estu" resolves.
- Bounded multi-turn memory resolves pronoun/ellipsis/narrowing follow-ups; scope is
  never carried across sessions/users (history is loaded per `SessionID`).
- Language detection (script) accuracy = **48/48** on the golden set; DB multi-turn
  memory test passes.

## 6. Voice + translation (Part E)

- Server-side adapter `app/zia_voice.py` (`ZiaVoice` ABC + `UnavailableZiaVoice`
  default + `CatalystZiaVoice` env-gated SDK impl) + `voice_capability_status()`.
- `/chat/capabilities` returns the truthful voice provider (`browser-web-speech`),
  the low-confidence threshold, and the platform-limitation + evidence note.
- Frontend: mic labelled **"Browser voice"** (never Zia); low-confidence dictation
  requires confirm/edit before executing; editing clears the gate.
- Translation (`/chat/translate`) is now **provider-neutral** (`_provider_chat`
  routes to QuickML LLM Serving when configured, else a self-hosted OpenAI-compatible
  runtime, else returns `available:false` — no fabrication, no commercial default).

## 7. Typed answer-visualization contract (Part F)

- Server-validated spec `services/ml/app/nlsql/viz.py` (`build_visualization` +
  `validate_spec`). Deterministic selection from result shape + intent; only the
  approved kinds may be emitted: **table, number, bar, line, choropleth, heatmap,
  timeline, network, sankey, link**. No model-authored JS/Vega/HTML is ever executed.
- Every spec carries: title, dimensions, measures + units, time/geography fields,
  source ids, an as-of timestamp + `dataset:"synthetic"` (freshness), a suppressed
  count, the scope role, confidence, and an always-present accessible-table fallback
  (`accessible_table.row_ref="rows_preview"`).
- Frontend `AnswerVisualization.tsx` renders each kind by reusing existing components
  (`TrendChart` for line/timeline, a themed Recharts bar, `districtChoropleth` +
  `MapCanvas` for choropleth/heatmap, a number tile, the shared data table for
  table/network/sankey/link with an "open in view" note). The accessible data table
  is always present; large results stay server-capped (`_ROWS_PREVIEW_CAP=50`,
  `nlsql_row_cap=200`) — the full database is never sent to the browser.

## 8. Evaluation & tests (Part G)

Versioned golden set: `services/ml/eval/golden_v1.json`
(`golden-nlsql-2026.07.21-1`). Offline deterministic runner:
`services/ml/eval/run_eval.py` (`python -m eval.run_eval`). Machine-readable snapshot:
`docs/phase-reports/PHASE_19_eval_report.json`.

Golden coverage: **25 English** NL, **23 Kannada/transliterated** NL, **10 multi-turn
chains**, 4 ambiguity, 7 guard (injection/DDL/dangerous-func), 8 scope (denial + allow),
8 visualization-selector, 10 spec-validity (every allowed kind), 3 prompt-injection/
unsupported-data.

Offline metrics (all rates, snapshot 2026-07-21):

| Metric | Rate |
|---|---|
| Intent / plan correctness | 1.00 (58/58) |
| Language (script) correctness | 1.00 (48/48) |
| Aggregate-only substitution | 1.00 |
| Visualization-kind correctness | 1.00 (51/51) |
| Multi-turn context carry | 1.00 (10/10) |
| Emitted-SQL guard validity | 1.00 (54/54) |
| Guard block (injection/DDL) | 1.00 (7/7) |
| Scope denial correctness | 1.00 (8/8) |
| Visualization spec validity | 1.00 (10/10) |
| Prompt-injection safety | 1.00 (3/3) |
| Planner latency (deterministic) | p50 0.06 ms / p95 0.60 ms |

Test suites (this session):

- Backend, full offline: **302 passed, 153 skipped, 0 failed** (`pytest`, DB tests skip).
- Backend NL→SQL with the synthetic DB configured: **63 passed** including 10
  `@requires_db` integration tests (read-only execution, grounded+cited+persisted
  answers, policymaker aggregate, multi-turn memory, voice-transcript persistence).
- New backend tests: `tests/test_nlsql_eval.py` (golden gate), `tests/test_prompt19.py`
  (scope flags, planner labelling, viz selector, capabilities, Zia honest-disable).
- Frontend: `npm run typecheck` clean; `npm run test` **18 files / 53 tests passed**,
  including `AnswerVisualization.test.tsx`, `Composer.voice.test.tsx`, and the
  deterministic-provider E2E `ask.e2e.test.tsx`.

**Citation validity** (that surfaced record ids resolve to real rows) and **execution
correctness** are exercised by the `@requires_db` integration tests above; the offline
harness proves the security guards + plan/viz contract that must hold regardless of
provider or data state.

## 9. Known limitations (honest)

- **Live QuickML LLM Serving is not invoked in this phase.** The adapter, provider-
  neutral config, fail-closed fallback and labelling are implemented and tested; the
  real endpoint call is a Prompt 23 step (§10). In the local/offline demo the
  deterministic planner is the honest primary and is labelled as such.
- **No headless-browser (Playwright) harness is installed.** The deterministic-
  provider E2E runs at the component-integration level (jsdom). A real browser E2E
  against the live provider is retained for Prompt 23.
- **Zia voice/translation** is unavailable in the Catalyst IN DC; the browser Web
  Speech fallback depends on the user's browser (Chrome/Edge) and is labelled as such.
- Choropleth district matching is exact after trim+uppercase; a served spelling that
  differs from the bundled geojson shows neutral (no-data) fill but stays fully
  readable in the accessible table.
- The deterministic planner covers the common analyst intents (count / by-district /
  top / trend / list); genuinely novel phrasings are handled by the QuickML planner
  when live, and otherwise produce an honest clarification.

## 10. Exact Prompt 23 live-verification steps

1. Deploy/confirm a QuickML LLM Serving model (e.g. a Qwen 2.5 Instruct deployment)
   in the DHRISTI IN-DC project; capture the endpoint + model id (no secret) as
   evidence.
2. Set server-side env on AppSail (never in the browser): `SEMANTIC_PLANNER_PROVIDER=
   catalyst_quickml`, `QUICKML_LLM_ENDPOINT=…`, `QUICKML_LLM_MODEL=…`, `QUICKML_LLM_API_KEY=…`.
3. Call `GET /chat/capabilities` on the deployment; confirm
   `semantic_planner.primary == "catalyst-quickml-llm"` and `quickml_llm_configured=true`.
4. Run a bilingual multi-turn conversation (EN + Kannada + one transliterated) via
   `POST /chat/ask`; confirm `planner_source=="catalyst-quickml-llm"`,
   `planner_degraded=false`, grounded citations, and a trend + a choropleth answer.
5. Verify aggregate-only isolation live (policymaker role header) and that a crafted
   PII/DDL request is refused server-side.
6. Re-run the golden set against the live provider and record intent/citation/latency
   (p50/p95) deltas vs the deterministic baseline in this report.
7. Add + run a headless-browser (Playwright) E2E against the deployed SPA + live
   provider; retain it as the live regression test.
8. Confirm Zia voice availability in the IN DC at that time; if still absent, keep the
   labelled browser fallback and record the re-checked evidence.

## 11. Files changed (this phase)

Backend: `services/ml/app/config.py`, `nlsql/planner.py`, `nlsql/engine.py`,
`nlsql/viz.py` (new), `zia_voice.py` (new), `chat/{router,service,schemas}.py`,
`predict/placement.py`, `tests/test_nlsql.py` (source label), `tests/test_prompt19.py`
(new), `tests/test_nlsql_eval.py` (new), `eval/golden_v1.json` + `eval/run_eval.py` +
`eval/__init__.py` (new).

Frontend: `web/src/api/types.ts`, `api/endpoints/chat.ts`, `stores/useAskStore.ts`,
`components/ask/Composer.tsx`, `components/ask/AnswerCard.tsx`,
`components/ask/AnswerVisualization.tsx` (new), `components/map/layers.ts`,
`routes/ask/ChatView.tsx`, and tests under `components/ask/__tests__/`.

Infra/docs: `infra/catalyst/ml-placement.json`, `infra/catalyst/COMPONENTS.md`,
`.env.example`, `docs/phase-reports/PHASE_19_eval_report.json`.
