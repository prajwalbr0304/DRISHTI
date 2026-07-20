# Phase artifact contract

Each Prompt 19-26 phase owns `artifacts/phase-XX/` containing:

- `preflight.json`: branch, dirty paths, dependency status, timestamp;
- `agent-runs.json`: agent, scope, writable paths, commands, result, blockers, artifacts;
- `test-summary.json`: tier, command, exit code, counts, duration, log path;
- `evidence.jsonl` and `evidence-manifest.json`;
- phase-specific evaluation, cloud, security, load, or recovery evidence.

Keep full logs out of chat. Do not store credentials, environment values, raw evidence, unrestricted narratives, hidden reasoning, or real PII. Hash immutable evidence artifacts with SHA-256.

`EXECUTION_STATE.json` is the authority for phase dependencies. Reports describe results but do not override the state machine or strict gate.
