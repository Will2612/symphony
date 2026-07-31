# Dispatch for Worker M6 (Agent Execution & Codex Protocol Doc)

## Identity
- Role: Documentation Worker M6
- Working Directory: /home/will/Projects/symphony/.agents/teamwork_preview_worker_m6
- Target File: /home/will/Projects/symphony/docs/06_agent_execution_and_codex.md

## Context & Inputs
- Original Request: `/home/will/Projects/symphony/.agents/ORIGINAL_REQUEST.md`
- Survey Analysis 1: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_1/analysis.md`
- Survey Analysis 2: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_2/analysis.md`
- Survey Analysis 3: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_3/analysis.md`

## Instructions
1. Write detailed Markdown documentation in `/home/will/Projects/symphony/docs/06_agent_execution_and_codex.md` covering:
   - `SymphonyElixir.AgentRunner`: Task Supervisor execution, multi-turn loop (`run_codex_turns/5`), `max_turns` limit enforcement.
   - `SymphonyElixir.PromptBuilder`: Solid template interpolation of Liquid variables (`{{ issue.identifier }}`, `{{ issue.title }}`, `{{ issue.description }}`).
   - Codex App-Server JSON-RPC 2.0 Protocol (`SymphonyElixir.Codex.AppServer`): Subprocess stdio/SSH streaming, RPC method calls (`initialize`, `thread/start`, `turn/start`), notification handling (`thread/created`, `turn/completed`), approval policies (`approval_policy`).
   - Dynamic Tool Execution: `SymphonyElixir.Codex.DynamicTool` client-side execution (`linear_graphql` tool spec, request routing, result response).
2. **Mermaid Diagram Requirement**: Embed at least one valid Mermaid sequence diagram (`sequenceDiagram`) depicting Codex JSON-RPC app-server turn execution, notifications, and dynamic tool calls.
3. Verify Mermaid syntax and ensure accurate details reflecting codebase.
4. Write your handoff report to `/home/will/Projects/symphony/.agents/teamwork_preview_worker_m6/handoff.md`.
5. Send a message to orchestrator upon completion.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
