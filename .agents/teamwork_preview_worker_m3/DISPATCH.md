# Dispatch for Worker M3 (Issue Tracker Integration Doc)

## Identity
- Role: Documentation Worker M3
- Working Directory: /home/will/Projects/symphony/.agents/teamwork_preview_worker_m3
- Target File: /home/will/Projects/symphony/docs/03_issue_tracker_integration.md

## Context & Inputs
- Original Request: `/home/will/Projects/symphony/.agents/ORIGINAL_REQUEST.md`
- Survey Analysis 1: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_1/analysis.md`
- Survey Analysis 2: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_2/analysis.md`
- Survey Analysis 3: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_3/analysis.md`

## Instructions
1. Write detailed Markdown documentation in `/home/will/Projects/symphony/docs/03_issue_tracker_integration.md` covering:
   - Issue Tracker Abstraction: `SymphonyElixir.Tracker` behaviour contract.
   - Linear Integration: `SymphonyElixir.Linear.Adapter`, `SymphonyElixir.Linear.Client` (GraphQL queries: `SymphonyLinearPoll`, `SymphonyLinearIssuesById`, `SymphonyLinearViewer`; mutations: `commentCreate`, `issueUpdate`, state resolution).
   - Mock Adapter: `SymphonyElixir.Tracker.Memory` for testing and offline development.
   - Core Data Model: `SymphonyElixir.Linear.Issue` struct attributes (`id`, `identifier`, `title`, `description`, `priority`, `state`, `branch_name`, `url`, `assignee_id`, `blocked_by`, `labels`, `assigned_to_worker`).
2. **Mermaid Diagram Requirement**: Embed at least one valid Mermaid sequence diagram (`sequenceDiagram`) or class diagram illustrating Linear GraphQL interaction flow and Tracker behaviour polymorphism.
3. Verify Mermaid syntax and ensure accurate details reflecting codebase.
4. Write your handoff report to `/home/will/Projects/symphony/.agents/teamwork_preview_worker_m3/handoff.md`.
5. Send a message to orchestrator upon completion.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
