# Dispatch for Worker M7 (Observability & Web UI Doc)

## Identity
- Role: Documentation Worker M7
- Working Directory: /home/will/Projects/symphony/.agents/teamwork_preview_worker_m7
- Target File: /home/will/Projects/symphony/docs/07_observability_and_ui.md

## Context & Inputs
- Original Request: `/home/will/Projects/symphony/.agents/ORIGINAL_REQUEST.md`
- Survey Analysis 1: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_1/analysis.md`
- Survey Analysis 2: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_2/analysis.md`
- Survey Analysis 3: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_3/analysis.md`

## Instructions
1. Write detailed Markdown documentation in `/home/will/Projects/symphony/docs/07_observability_and_ui.md` covering:
   - Terminal UI Dashboard (`SymphonyElixir.StatusDashboard`): ANSI status lines, throughput sparklines, real-time terminal output.
   - Phoenix Web Interface (`SymphonyElixirWeb`): Phoenix Endpoint (`HttpServer`), Router, LiveView (`DashboardLive`), static asset pipeline (`dashboard.css`).
   - PubSub Event Broadcasting: `SymphonyElixirWeb.ObservabilityPubSub` broadcasting on `"observability:dashboard"` topic.
   - Observability REST API: `ObservabilityApiController` routes (`GET /api/v1/state`, `POST /api/v1/refresh`, `GET /api/v1/:issue_identifier`), JSON payload schemas.
2. **Mermaid Diagram Requirement**: Embed at least one valid Mermaid diagram (e.g. `sequenceDiagram` or `graph LR`) showing the PubSub event flow and Web LiveView / REST observability data stream.
3. Verify Mermaid syntax and ensure accurate details reflecting codebase.
4. Write your handoff report to `/home/will/Projects/symphony/.agents/teamwork_preview_worker_m7/handoff.md`.
5. Send a message to orchestrator upon completion.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
