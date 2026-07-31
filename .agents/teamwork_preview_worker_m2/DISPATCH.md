# Dispatch for Worker M2 (Workflow & Config Doc)

## Identity
- Role: Documentation Worker M2
- Working Directory: /home/will/Projects/symphony/.agents/teamwork_preview_worker_m2
- Target File: /home/will/Projects/symphony/docs/02_workflow_and_config.md

## Context & Inputs
- Original Request: `/home/will/Projects/symphony/.agents/ORIGINAL_REQUEST.md`
- Survey Analysis 1: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_1/analysis.md`
- Survey Analysis 2: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_2/analysis.md`
- Survey Analysis 3: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_3/analysis.md`

## Instructions
1. Write detailed Markdown documentation in `/home/will/Projects/symphony/docs/02_workflow_and_config.md` covering:
   - `WORKFLOW.md` Specification: Front-matter YAML configuration and Liquid prompt body template.
   - `SymphonyElixir.Workflow`: Parsing workflow files, YAML decoding (`YamlElixir`), prompt template extraction.
   - `SymphonyElixir.WorkflowStore`: In-memory caching agent and hot-reloading mechanism.
   - `SymphonyElixir.Config.Schema`: Ecto embedded schema definition (`Tracker`, `Polling`, `Workspace`, `Worker`, `Agent`, `Codex`, `Hooks`, `Observability`, `Server`).
   - Environment Variable Indirection (`$LINEAR_API_KEY`, `$SYMPHONY_WORKSPACE_ROOT`, etc.) and validation rules.
2. **Mermaid Diagram Requirement**: Embed at least one valid Mermaid diagram (e.g. `classDiagram` or `graph LR`) mapping out the Ecto Config schema structure and Workflow parsing pipeline.
3. Verify Mermaid syntax and ensure accurate details reflecting codebase.
4. Write your handoff report to `/home/will/Projects/symphony/.agents/teamwork_preview_worker_m2/handoff.md`.
5. Send a message to orchestrator upon completion.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
