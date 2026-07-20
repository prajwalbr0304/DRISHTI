# DRISHTI execution decisions

This file is the compact, cross-session decision log for `prompt3new.md`. Add only
decisions that constrain later phases; keep investigation detail in phase artifacts.

## Active decisions

- Prompt 18 completed on 20 July 2026; its evidence is in
  `docs/phase-reports/PHASE_18_REPORT.md`. Execute Prompt 19 through Prompt 25 in order,
  then run Prompt 26 as a fresh independent audit.
- The existing Catalyst project is DHRISTI, project `48361000000030003`, organization
  `60075362708`, India DC. Do not create a duplicate project.
- Use AWS profile `drishti`; inventory and reuse resources before bounded mutation.
- Catalyst owns deployed operational serving data. AWS remains the protected historical,
  analytics, geospatial, and justified custom-ML plane.
- RLS/FORCE RLS stays disabled for this synthetic hackathon only; server-side role and
  scope authorization remains mandatory.
- Voice questions may be enabled. OCR, evidence extraction, face/object recognition,
  and evidence-media transcription remain out of hackathon scope.
- Completion requires real evidence; mocks, descriptors, and future-tense plans cannot
  satisfy a mandatory live gate.
- The release label is HACKATHON-DEMO READY, never production-ready.

## Decision entry format

Record date, phase, decision, authoritative source, affected contracts/paths, and any
superseded decision. Never put credentials or personal data here.

## Prompt 19 decisions (2026-07-21)

- Ask DRISHTI semantic planner is **Catalyst QuickML LLM Serving** (primary in the
  live-ready contract; QuickML LLM Serving is available in the IN DC and hosts open
  models such as Qwen 2.5). Provider-neutral settings; the `gpt-4o-mini` implied
  default is removed; the engine fails closed to a **labelled** deterministic planner
  (`planner_source`/`planner_degraded`) rather than a silent commercial API. Live
  invocation is verified in **Prompt 23**.
  Source: https://docs.catalyst.zoho.com/en/quickml/help/generative-ai/llm-serving/
- **Catalyst Zia does not expose speech-to-text / text-to-speech / translation** in
  the IN DC, so the submitted voice capability is the browser Web Speech API (labelled
  as browser voice, never Zia); bilingual EN/KN text always works. An env-gated Zia
  adapter contract (`DRISHTI_USE_CATALYST_ZIA_VOICE`) is ready if that changes.
  Source: https://docs.catalyst.zoho.com/en/zia-services/getting-started/components-of-zia-services/
- Voice query dictation is IN scope (`QUERY_VOICE_ENABLED=true`), strictly separate
  from evidence extraction (`EVIDENCE_EXTRACTION_ENABLED=false`, stays off).
- Ask answers carry a **server-validated typed visualization spec** (approved kinds
  only; never model-authored code) with an always-present accessible-table fallback.
- Low-confidence voice dictation must be confirmed/edited before it executes.
