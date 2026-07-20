# DRISHTI Kiro agents and skills

This workspace contains purpose-built Kiro agents in `agents/` and progressively loaded
skills in `skills/`. The original `prompt3.md` is unchanged; use `../prompt3new.md` for
the orchestrated Prompt 19-26 workflow.

## Start a session

1. Open this repository as a trusted Kiro workspace. Kiro may show one workspace-trust
   confirmation the first time because agents can execute tools.
2. Run Prompt 18 with the primary agent for the one-time baseline reconciliation.
3. For Prompts 19-25, select `drishti-orchestrator` from the agent selector.
4. Start with: `/phase-runner execute the next Pending prompt from prompt3new.md`.
5. For Prompt 26, open a fresh chat and select `evidence-auditor`.

Kiro discovers the skills as slash commands. Use `/context show` if a skill is missing.
Every custom agent explicitly includes `skill://.kiro/skills/*/SKILL.md` so metadata is
loaded cheaply and full instructions are loaded only when invoked.

## Permission behavior

Built-in tools available to each agent are pre-approved through documented Kiro agent
permission rules. Agent-specific hard denies still block destructive git/project actions,
cross-cloud commands, and secret-file access. Read-only auditors do not have the `write`
tool. Interactive Zoho/AWS sign-in and Kiro workspace trust can still require user action.

Do not add a global wildcard agent to suppress those protections. Add the narrow command
or path to the relevant specialist only after reviewing its effect.
