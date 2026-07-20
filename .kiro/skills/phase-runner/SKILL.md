---
name: phase-runner
description: Run DRISHTI Prompt 19-26 phase preflight, dependency checks, execution-state updates, artifact initialization, strict handoff, and next-session preparation. Use when starting, resuming, checking, or handing off a prompt3new phase.
---

# DRISHTI Phase Runner

Execute exactly one phase per primary session.

## Start or resume a phase

1. Run `scripts/phase_state.py preflight --repo <root> --phase <19-26>`.
2. Stop if the preceding phase is not `complete`; do not bypass the dependency by editing state.
3. Read only:
   - `EXECUTION_STATE.json`;
   - `docs/execution/FILE_MAP.json`;
   - `docs/execution/DECISIONS.md`;
   - `docs/execution/NEXT_SESSION.md`;
   - `docs/execution/RELEASE_REQUIREMENTS.json`;
   - the selected phase in `prompt3new.md`;
   - current `git status --short`.
4. Consult `prompt2.md` and historical reports only for a cited requirement or contradiction.
5. Initialize `artifacts/phase-XX/` and define one writable owner per path.

Use the artifact contract in `references/phase-artifacts.md`.

## Execute

- Parallelize bounded read-only inventory, test investigation, and security review.
- Freeze shared contracts before backend/frontend implementation.
- Use one cloud operator sequentially and inventory before mutation.
- Record complete outputs as artifacts; return concise summaries to chat.
- Run targeted gates after each change and the affected full gates before completion.

## Handoff

Run:

```text
python .kiro/skills/phase-runner/scripts/phase_state.py handoff \
  --repo <root> --phase <N> --status <in_progress|pending|complete> \
  --next-action "<single concrete action>"
```

Set `complete` only after the Definition of Done, report, evidence manifest, and strict gate all pass. Never convert held, manual, unknown, skipped, scaffolded, or unconfigured work into completion.
