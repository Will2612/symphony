# Handoff Report — Explorer 3 (APIs, Interfaces & Module Dependencies)

**Agent Role**: Codebase Explorer 3 (APIs, Interfaces & Module Dependencies)  
**Working Directory**: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_3`  
**Target Path**: `/home/will/Projects/symphony`  
**Date**: 2026-07-31  

---

## 1. Observation

Direct code observations from the `/home/will/Projects/symphony/elixir` codebase:

1. **OTP Supervision Tree & Entry Points**:
   - `lib/symphony_elixir.ex` (lines 26-39): `SymphonyElixir.Application.start/2` initializes `Phoenix.PubSub`, `Task.Supervisor` (`SymphonyElixir.TaskSupervisor`), `SymphonyElixir.WorkflowStore`, `SymphonyElixir.Orchestrator`, `SymphonyElixir.HttpServer`, and `SymphonyElixir.StatusDashboard`.
   - `lib/symphony_elixir/cli.ex` (lines 21-49): `SymphonyElixir.CLI.main/1` parses CLI switches (`--port`, `--logs-root`, `--i-understand-that-this-will-be-running-without-the-usual-guardrails`), loads `WORKFLOW.md`, and calls `Application.ensure_all_started(:symphony_elixir)`.

2. **Orchestrator Control Loop & Concurrency**:
   - `lib/symphony_elixir/orchestrator.ex` (lines 53-118, 246-298): GenServer loop triggered by `:tick` / `:run_poll_cycle`. Reconciles active running and blocked issues, queries candidate issues via `Tracker.fetch_candidate_issues/0`, sorts by priority & creation date, and spawns `AgentRunner.run/3` via `Task.Supervisor`.
   - `lib/symphony_elixir/orchestrator.ex` (lines 557-614, 1006-1043): Reconciles stalled sessions (`stall_timeout_ms`), handles agent termination, and schedules exponential backoff retries via `Process.send_after(self(), {:retry_issue, ...}, delay_ms)`.

3. **External API Integrations**:
   - **Linear GraphQL API**: `lib/symphony_elixir/linear/client.ex` (lines 12-104) defines GraphQL queries `SymphonyLinearPoll`, `SymphonyLinearIssuesById`, and `SymphonyLinearViewer`. `lib/symphony_elixir/linear/adapter.ex` (lines 10-38) defines mutations `commentCreate`, `issueUpdate`, and query `resolveStateId`.
   - **Codex App-Server Protocol**: `lib/symphony_elixir/codex/app_server.ex` (lines 241-326) implements JSON-RPC 2.0 protocol (`initialize`, `thread/start`, `turn/start`). Handles auto-approvals, dynamic tool calls (`item/tool/call`), and non-interactive user input prompts.
   - **SSH Remote Execution**: `lib/symphony_elixir/ssh.ex` (lines 5-48) provides `SSH.run/3` and `SSH.start_port/3` to execute commands and open stdio ports over SSH to remote worker hosts (`ssh -T`).

4. **Web & Observability REST / LiveView Interfaces**:
   - `lib/symphony_elixir_web/router.ex` (lines 17-40): Configures routes for Phoenix LiveView dashboard (`/`), static assets (`/dashboard.css`, `/vendor/*`), and REST API endpoints (`GET /api/v1/state`, `POST /api/v1/refresh`, `GET /api/v1/:issue_identifier`).
   - `lib/symphony_elixir_web/observability_pubsub.ex` (lines 6-24): Uses `Phoenix.PubSub` on topic `"observability:dashboard"` to broadcast `:observability_updated` whenever state snapshot changes occur.

5. **Dynamic Tools & Prompt Templating**:
   - `lib/symphony_elixir/codex/dynamic_tool.ex` (lines 8-54): Exposes `linear_graphql` tool to Codex for querying/modifying Linear issue data directly during turns.
   - `lib/symphony_elixir/prompt_builder.ex` (lines 11-26): Uses Solid engine (`Solid.render!`) to fill Liquid variables (`{{ issue.identifier }}`, `{{ issue.title }}`, `{{ issue.description }}`) into turn prompts.

---

## 2. Logic Chain

1. **Premise 1**: The initial user request (R1, R2, R3 in `ORIGINAL_REQUEST.md`) requires generating comprehensive documentation in `docs/` with Mermaid diagrams for architecture, module dependencies, APIs, and sequence flows.
2. **Premise 2**: Explorer 3's specific dispatch assignment is to analyze module dependencies, external API interfaces, web/HTTP routes, event/message handlers, CLI interfaces, sequence flows, and prepare complete Mermaid diagram models.
3. **Reasoning Step**: By examining all source files under `elixir/lib/symphony_elixir` and `elixir/lib/symphony_elixir_web`, we mapped out every inter-module interaction, process boundary, HTTP endpoint, JSON-RPC method, GraphQL operation, CLI switch, and GenServer message.
4. **Deduction**: The complete evidence chain has been synthesized in `analysis.md`, providing 6 Mermaid sequence diagrams (Startup, Dispatch, Codex Turn Loop, Dynamic Tool, Reconcile/Backoff, Observability PubSub), 2 Mermaid state machines (Orchestrator & Codex Turn), REST JSON payload schemas, and module dependency maps.

---

## 3. Caveats

1. **Elixir Project Location**: The source code is located under `/home/will/Projects/symphony/elixir/lib/`, not in the repository root. All documentation and diagrams reflect the Elixir implementation in `elixir/`.
2. **Dynamic Tool Capabilities**: Currently, `SymphonyElixir.Codex.DynamicTool` exposes a single client-side dynamic tool (`linear_graphql`). Additional dynamic tools can be added to `DynamicTool.tool_specs/0`.
3. **Execution Mode**: Explorer role operates under read-only constraints; no source code changes were made to `elixir/`.

---

## 4. Conclusion

The analysis of Symphony's APIs, interfaces, inter-module dependencies, and sequence flows is complete. All findings have been compiled into `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_3/analysis.md`.

Key architectural insights:
- Clean OTP supervision hierarchy isolating polling (`Orchestrator`), dynamic task execution (`Task.Supervisor`), web serving (`HttpServer`), and state UI (`StatusDashboard`).
- Decoupled issue tracker abstraction (`Tracker` behaviour with `Linear.Adapter` / `Tracker.Memory`).
- Robust JSON-RPC 2.0 stdio/SSH protocol handler in `Codex.AppServer` supporting local and remote SSH workers.
- Real-time observability via Phoenix LiveView (`DashboardLive`), PubSub (`ObservabilityPubSub`), and REST JSON API (`ObservabilityApiController`).

---

## 5. Verification Method

To independently verify the observations and logic chain:

1. **Verify Supervision Tree and Modules**:
   ```bash
   cd /home/will/Projects/symphony/elixir
   mix test
   ```
2. **Verify Module Dependencies & Compilation**:
   ```bash
   cd /home/will/Projects/symphony/elixir
   mix compile --warnings-as-errors
   ```
3. **Inspect Output Artifacts**:
   - Confirm analysis report exists: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_3/analysis.md`
   - Confirm handoff report exists: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_3/handoff.md`
