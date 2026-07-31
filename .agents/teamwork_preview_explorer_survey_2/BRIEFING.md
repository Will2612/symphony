# BRIEFING — 2026-07-31T21:32:55+08:00

## Mission
Explore `/home/will/Projects/symphony` source files to identify core business domains, core data models, key services, and business logic modules. Categorize all core functionality into logical business domains and produce analysis.md and handoff.md.

## 🔒 My Identity
- Archetype: Explorer
- Roles: Explorer 2 (Core Business Domains & Logic)
- Working directory: /home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_2
- Original parent: 5ebf6aa6-a8a8-44e2-8e8d-4e1289a30bfc
- Milestone: Explorer Survey

## 🔒 Key Constraints
- Read-only investigation — do NOT implement code changes in the project repository
- Focus on business domains, core data models, key services, workflows, and business logic modules
- Write output to analysis.md and handoff.md in working directory

## Current Parent
- Conversation ID: 5ebf6aa6-a8a8-44e2-8e8d-4e1289a30bfc
- Updated: 2026-07-31T21:32:55+08:00

## Investigation State
- **Explored paths**: `SPEC.md`, `README.md`, `elixir/lib/symphony_elixir/`, `elixir/lib/symphony_elixir_web/`, `elixir/test/`
- **Key findings**: Identified 6 primary business domains (Workflow & Policy, Tracker Integration, Orchestration Engine, Workspace & Sandbox, Agent Execution & Codex, Observability Surface), full state machine, data models (`Issue`, `Config.Schema`, `Orchestrator.State`, `Workspace`, `LiveSession`), and execution workflow logic.
- **Unexplored areas**: None within scope.

## Key Decisions Made
- Categorized codebase into 6 distinct business domains.
- Documented full architectural details in `analysis.md` and `handoff.md`.

## Artifact Index
- DISPATCH.md — Initial dispatch instructions
- BRIEFING.md — Working memory state
- progress.md — Liveness heartbeat and progress tracking
- analysis.md — Detailed core business domains & logic analysis report
- handoff.md — 5-component handoff report for orchestrator
