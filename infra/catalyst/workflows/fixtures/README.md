# Workflow synthetic fixtures (Phase 14)

One end-to-end synthetic fixture per workflow (see `docs/phase-reports/
PHASE_14_WORKFLOWS.md`). Each fixture is `{workflow, fixture_status,
idempotency_key, input, expected_output, lineage, asserts}` — the acceptance
contract for that workflow. All data is synthetic (no PII).

- **runnable** (`wf01`, `wf02`, `wf10`, `wf11`) — the referenced code executes
  locally today and was verified (smoke test, ds-import importer, offline RAG
  cited-answer/PII-refusal, SmartBrowz watermarked render + sha256).
- **representative** (`wf03`–`wf09`, `wf12`, `wf17`, `wf18`) — committed
  input/expected contract; runs end-to-end once the owning component is deployed +
  enabled (`wf12` is the Node notify template contract).
- **deferred** — workflows **13–16** (Investigation Board / Disaster Response)
  have **no** fixture here by the phase-order rule; Prompt 16 (wf13) and Prompt 17
  (wf14–16) supply them. Their contracts are still specified in the workflow doc.

Fixtures 13–16 are intentionally absent (not a gap): creating them would imply
those workflows are functional in Prompt 14, which the phase-order rule forbids.
