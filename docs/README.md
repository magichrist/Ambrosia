# Ambrosia Builder Plan Bundle

This bundle is the initial implementation plan for Ambrosia, a Python context-driven automation workbench with an adaptive TUI, typed artifacts, actions, presets, phases, and a Windows-first assessment pack.

## Recommended reading order

1. `00_MASTER_PLAN.md` — product definition, architecture, stack, safety boundary, MVP, and overall roadmap.
2. `01_SHARED_CONTRACTS.md` — the API/data contracts all builder agents must follow.
3. `05_ORCHESTRATOR_PROMPT.md` — paste this into the lead/orchestrator coding agent.
4. `02_BUILDER_AGENT_WORK_PACKAGES.md` — specialist builder agent prompts, ownership, dependencies, tests, and acceptance criteria.
5. `03_ROADMAP_AND_ACCEPTANCE.md` — milestones and end-to-end test scenarios.
6. `04_DECISIONS_AND_OPEN_QUESTIONS.md` — settled architecture decisions and questions for the lead.
7. `06_FIRST_SPRINT_BACKLOG.md` — initial implementation tickets.

## How to use with builder agents

- Start with one lead/orchestrator agent.
- Have the lead inspect the existing repository and freeze shared contracts before parallel work.
- Assign one specialist work package per agent, with the shared plan and contract documents as context.
- Keep agents in separate branches/worktrees and enforce the file ownership boundaries.
- Integrate in the dependency waves described in `02_BUILDER_AGENT_WORK_PACKAGES.md`.
- Require each agent to submit the handoff report template in that document.

## First expected product milestone

A working vertical slice: create an engagement and scope, add a target, run a bounded read-only discovery action (or a fixture-backed fake), parse structured output into typed artifacts, persist execution history, update context, surface new relevant actions, validate a preset, and export evidence.

The plan intentionally keeps the first built-in Windows pack read-only and explicitly scoped. User-authored command and script actions are represented as separately declared, reviewed action assets; code is not evaluated from preset YAML.
