# Dispatch for Worker M5 (Workspace Management Doc)

## Identity
- Role: Documentation Worker M5
- Working Directory: /home/will/Projects/symphony/.agents/teamwork_preview_worker_m5
- Target File: /home/will/Projects/symphony/docs/05_workspace_management.md

## Context & Inputs
- Original Request: `/home/will/Projects/symphony/.agents/ORIGINAL_REQUEST.md`
- Survey Analysis 1: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_1/analysis.md`
- Survey Analysis 2: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_2/analysis.md`
- Survey Analysis 3: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_3/analysis.md`

## Instructions
1. Write detailed Markdown documentation in `/home/will/Projects/symphony/docs/05_workspace_management.md` covering:
   - `SymphonyElixir.Workspace`: Per-issue working directory manager (`create_for_issue/2`, `path_for_issue/2`, cleanup).
   - Path Safety Guardrails: `SymphonyElixir.PathSafety` path canonicalization and directory containment validation.
   - Workspace Lifecycle Hooks: `after_create`, `before_run`, `after_run`, `before_remove` shell command execution.
   - Remote Worker Execution: `SymphonyElixir.SSH` SSH command execution and remote workspace directory setup over SSH stdio ports.
2. **Mermaid Diagram Requirement**: Embed at least one valid Mermaid sequence diagram (`sequenceDiagram`) or flowchart illustrating Workspace Creation, Lifecycle Hook Execution, and Path Safety Checks.
3. Verify Mermaid syntax and ensure accurate details reflecting codebase.
4. Write your handoff report to `/home/will/Projects/symphony/.agents/teamwork_preview_worker_m5/handoff.md`.
5. Send a message to orchestrator upon completion.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
