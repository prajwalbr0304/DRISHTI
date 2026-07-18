"""FIR/case structured intake (Phase 2).

Contextual intake for the DRISHTI React UI + FastAPI: draft create/update/
validate, duplicate/source-key checks, canonical case-party roles, submit for
review, supervisor approve/reject/return, workflow-gated case events, and the
reference/option lookups the wizard renders from.

All writes go through the read/write DB layer (app.db.rw_conn), are guarded to
localhost + a synthetic-marked database (app.intake.guards), and the canonical
case-creating transitions stay behind a submit gate until Prompt 3 finalises the
hackathon access path. Category-specific lifecycles are validated server-side
against the CaseCategoryWorkflow state machine — never merely hidden in the UI.
"""
