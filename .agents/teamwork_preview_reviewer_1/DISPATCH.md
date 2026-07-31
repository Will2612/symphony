# Dispatch for Reviewer 1 (Documentation Review)

## Identity
- Role: Documentation Reviewer 1
- Working Directory: /home/will/Projects/symphony/.agents/teamwork_preview_reviewer_1

## Context & Inputs
- Original Request: `/home/will/Projects/symphony/.agents/ORIGINAL_REQUEST.md`
- Scope Document: `/home/will/Projects/symphony/.agents/orchestrator/PROJECT.md`
- Target Directory: `/home/will/Projects/symphony/docs/`

## Instructions
1. Review all 7 documentation files in `/home/will/Projects/symphony/docs/`:
   - `docs/01_architecture_overview.md`
   - `docs/02_workflow_and_config.md`
   - `docs/03_issue_tracker_integration.md`
   - `docs/04_orchestration_engine.md`
   - `docs/05_workspace_management.md`
   - `docs/06_agent_execution_and_codex.md`
   - `docs/07_observability_and_ui.md`
2. Verify that:
   - Every file exists and is comprehensive.
   - Every file contains at least one Mermaid diagram block (e.g. ````mermaid ... ````).
   - Every Mermaid diagram syntax is valid.
   - The documentation accurately reflects the Elixir codebase in `/home/will/Projects/symphony/elixir`.
3. Write your detailed review to `/home/will/Projects/symphony/.agents/teamwork_preview_reviewer_1/analysis.md` and handoff report with verdict `APPROVE` or `REQUEST_CHANGES` to `/home/will/Projects/symphony/.agents/teamwork_preview_reviewer_1/handoff.md`.
4. Notify orchestrator via `send_message`.
