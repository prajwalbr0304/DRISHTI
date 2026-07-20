"""Live Command Center committed-FIR event flow (Prompt 20 Part E).

Defines the committed new-FIR flow:

    approved canonical write -> case.committed event -> projection/feature
    invalidation -> eligible analytics recompute -> alert/dashboard refresh.

Events are idempotent (a duplicate case.committed is suppressed), and the flow
exposes source timestamp, processed timestamp, freshness and last-success/failure
state per projection. Locally this is a polled projection ledger; in Prompt 23 it
integrates through the single Catalyst Signal (case.committed) and the scoped
update channel.

Hard guarantees: a committed FIR updates ONLY aggregate projections (district
statistic, supervisor workload, eligible hotspot/near-repeat). It NEVER rescores
an individual person and NEVER auto-dispatches staff.
"""
