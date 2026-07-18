# infra/catalyst/jobs — Job Scheduling + Signals registry (Phase 14 Part B)

Descriptors for the event/schedule plane (matrix rows 20, 21, 22). Both files are
**reviewed sources of intent**, not auto-deployed: Catalyst crons are created via
the Job Scheduling SDK/Console, and Signals is entirely Console-configured (no
SDK). Everything here is **disabled/inactive** so it is cost-free until its
owning phase enables it.

## `cron-schedules.json` — Job Scheduling / Cron (row 20, workflows §9, §17, §18)

Two active-phase crons (`drishti-reconcile-nightly`, `drishti-forecast-daily`)
plus reserved disabled entries for later phases. All `enabled: false`. Enabling a
cron requires (a) registering the schedule in the Console/SDK and (b) setting the
matching AppSail `DRISHTI_*_ENABLED` env flag, so a schedule can never fire into
an inert handler.

## `signals-rules.json` — Signals publishers + rules (rows 21, 22)

Publishers: Stratus (evidence uploads), Data Store (canonical/prediction row
events), Authentication (signup), and a custom `drishti_app` publisher for
`report.ready` / `notify.requested` / `prediction.requested`. Rules route events
to the target functions in `../functions/`. Every rule is `active: false`. Retry
is auto (exponential backoff, max 20); undelivered events move to Dropped after
the 24h TTL — the Signals-native DLQ equivalent.

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
report). Multi-step orchestration therefore uses idempotent Functions + Job
Scheduling with the canonical idempotency key
`<task>:<subject>:<cutoff>:<feature-schema-version>:<model-version>:<source-version-hash>`.
