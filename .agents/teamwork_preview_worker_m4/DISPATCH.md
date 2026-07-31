# Dispatch for Worker M4 (Core Orchestration Engine Doc)

## Identity
- Role: Documentation Worker M4
- Working Directory: /home/will/Projects/symphony/.agents/teamwork_preview_worker_m4
- Target File: /home/will/Projects/symphony/docs/04_orchestration_engine.md

## Context & Inputs
- Original Request: `/home/will/Projects/symphony/.agents/ORIGINAL_REQUEST.md`
- Survey Analysis 1: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_1/analysis.md`
- Survey Analysis 2: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_2/analysis.md`
- Survey Analysis 3: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_3/analysis.md`

## Instructions
1. Write detailed Markdown documentation in `/home/will/Projects/symphony/docs/04_orchestration_engine.md` covering:
   - `SymphonyElixir.Orchestrator` GenServer Architecture & Responsibilities.
   - Polling Loop: Tick interval scheduling (`polling.interval_ms`), candidate issue selection, priority & creation date sorting.
   - Concurrency Management: Available slots calculation (`max_concurrent_agents`), active task tracking (`running`, `claimed`, `completed`, `blocked`).
   - Issue State Machine & Lifecycle: Transitions between candidate, running, completed, blocked, and retrying states.
   - Fault Tolerance & Retry Strategy: Exponential backoff retries (`retry_attempts`, `schedule_issue_retry`), stall detection (`stall_timeout_ms`), session reconciliation.
2. **Mermaid Diagram Requirement**: Embed at least one valid Mermaid state machine diagram (`stateDiagram-v2`) and/or polling sequence diagram (`sequenceDiagram`).
3. Verify Mermaid syntax and ensure accurate details reflecting codebase.
4. Write your handoff report to `/home/will/Projects/symphony/.agents/teamwork_preview_worker_m4/handoff.md`.
5. Send a message to orchestrator upon completion.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
