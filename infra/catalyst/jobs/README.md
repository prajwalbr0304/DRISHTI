# infra/catalyst/jobs — Job Scheduling + Signals registry (Phase 14 Part B + H scoping)

Descriptors for the event/schedule plane (matrix rows 20, 21, 22). Both files are
**reviewed sources of intent**, not auto-deployed: Catalyst crons are created via
the Job Scheduling SDK/Console, and Signals is entirely Console-configured (no
SDK). Everything here is **disabled/inactive** so it is cost-free until its
owning phase enables it.

## Part H — minimal event processing

The hackathon keeps a deliberately small event plane. Each descriptor is tagged
with a `tier`:

- **`tier: "minimal"`** — the only two things enabled for the hackathon:
  - **one `prediction.requested` Signal/Event Function** — the `prediction-requested`
    rule → `prediction_event` (dispatch a committed `PredictionRequest` to the
    protected AWS adapter);
  - **one scheduled aggregate forecast job** — the `drishti-forecast-daily` cron →
    `cron_forecast`.
- **`tier: "optional"`** — documented but Inactive: per-upload/import/report events,
  the result-ready event, the canonical-version event, and the Mail/Push rules
  (`report-ready`, `notify-requested`, `user-signedup`) which belong to **Prompt 15**.
- **`tier: "reserved"`** — created + enabled by later prompts (§13 → Prompt 16;
  §14–§16 → Prompt 17).

Kept even in the minimal set: **retry + failed-job state** (auto exponential
backoff, max 20; a failed `prediction_event` sets `PredictionRequest.Status='failed'`)
and the **persist-authoritative-record-before-emit** invariant (a Data Store
`row_inserted` trigger fires only after the row commits; the custom `drishti_app`
publisher is emitted only after the AppSail transaction commits). **Circuits**,
extra events, Mail/Push and multiple crons/backfills are **deferred**.

## `cron-schedules.json` — Job Scheduling / Cron (row 20, workflows §9, §17, §18)

`drishti-forecast-daily` is the one `tier: "minimal"` cron; `drishti-reconcile-nightly`
and `drishti-embeddings-refresh-weekly` are `tier: "optional"`; §13–§16 are
`reserved`. All `enabled: false`. Enabling a cron requires (a) registering the
schedule in the Console/SDK and (b) setting the matching AppSail `DRISHTI_*_ENABLED`
env flag, so a schedule can never fire into an inert handler.

## `signals-rules.json` — Signals publishers + rules (rows 21, 22)

`prediction-requested` is the one `tier: "minimal"` rule (Data Store `row_inserted`
on a committed, approved `PredictionRequest` → `prediction_event`). All other rules
are `tier: "optional"` and `active: false`. Retry is auto (exponential backoff,
max 20); undelivered events move to Dropped after the 24h TTL — the Signals-native
DLQ equivalent.

## Phase-order rule (workflows 13–16)

Prompt 14 may create only **shared infra + disabled job definitions + reserved
namespaces + typed adapter contracts** for the Investigation Board (§13, Prompt
16) and Disaster Response (§14–§16, Prompt 17). Accordingly:

- `cron-schedules.json` carries `RESERVED` disabled entries for §13–§16 whose
  `function` is `null` (the owning function is created by Prompt 16/17).
- `signals-rules.json` lists `reserved_rules_later_phases` as inactive.
- No schedule or Signals rule for §13–§16 is enabled, so they incur no charge and
  are **not** claimed as functional. Prompt 16 enables §13; Prompt 17 enables
  §14–§16 with their domain migrations, UI, fixtures and acceptance tests.

## Why not Circuits

Branch/parallel workflow (matrix row 23) would normally use Catalyst Circuits,
but Circuits is **unavailable in the India DC** (re-verified; see the phase
report) and is **deferred** regardless (H optional). Multi-step orchestration uses
idempotent Functions + the one forecast cron with the canonical idempotency key
`<task>:<subject>:<cutoff>:<feature-schema-version>:<model-version>:<source-version-hash>`.
