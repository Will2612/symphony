# Handoff Report — Explorer 2 (Core Business Domains & Logic)

## 1. Observation

During read-only static analysis and directory structure investigation of `/home/will/Projects/symphony`, the following core components, file locations, structures, and implementations were directly observed:

1. **Repository Layout**:
   - `SPEC.md`: Root-level language-agnostic specification defining system architecture, entities (`Issue`, `Workflow Definition`, `Service Config`, `Workspace`, `Run Attempt`, `Live Session`, `Retry Entry`), and protocols.
   - `elixir/`: Elixir/BEAM implementation of Symphony containing `lib/symphony_elixir/`, `lib/symphony_elixir_web/`, `config/`, and `test/`.

2. **Core Domain Modules & Line Locations**:
   - **Orchestration & Dispatch Engine**:
     - `lib/symphony_elixir/orchestrator.ex:1-1922`: GenServer managing the poll loop (`handle_info(:run_poll_cycle, ...)`), issue dispatch, concurrency checks (`available_slots/1`), runtime state machine (`%State{running, claimed, completed, blocked, retry_attempts}`), issue reconciliation (`reconcile_running_issues/1`, `reconcile_blocked_issues/1`), and exponential backoff retry scheduling (`schedule_issue_retry/4`).
     - `lib/symphony_elixir.ex:15-47`: `SymphonyElixir.Application` OTP supervisor starting `PubSub`, `TaskSupervisor`, `WorkflowStore`, `Orchestrator`, `HttpServer`, and `StatusDashboard`.
   - **Workflow & Configuration Domain**:
     - `lib/symphony_elixir/workflow.ex:1-124`: Workflow loader parsing `WORKFLOW.md` front matter YAML and prompt Markdown templates.
     - `lib/symphony_elixir/workflow_store.ex`: In-memory OTP agent holding current workflow state with hot-reloading capability.
     - `lib/symphony_elixir/config/schema.ex:1-558`: Ecto embedded schemas (`Tracker`, `Polling`, `Workspace`, `Worker`, `Agent`, `Codex`, `Hooks`, `Observability`, `Server`) with validation, environment variable indirection (`$LINEAR_API_KEY`, `$SYMPHONY_WORKSPACE_ROOT`), and default value assignments.
   - **Tracker Integration Domain**:
     - `lib/symphony_elixir/linear/issue.ex:1-44`: Definition of `%SymphonyElixir.Linear.Issue{}` struct containing fields `id`, `identifier`, `title`, `description`, `priority`, `state`, `branch_name`, `url`, `assignee_id`, `blocked_by`, `labels`, `assigned_to_worker`.
     - `lib/symphony_elixir/linear/client.ex`: Low-level GraphQL HTTP client built on Finch.
     - `lib/symphony_elixir/linear/adapter.ex`: High-level queries mapping GraphQL responses into Issue structs.
     - `lib/symphony_elixir/tracker.ex`: Behaviour defining standard fetch functions.
   - **Workspace & Path Safety Domain**:
     - `lib/symphony_elixir/workspace.ex:1-484`: Workspace manager executing per-issue directory creation (`create_for_issue/2`), hook execution (`after_create`, `before_run`, `after_run`, `before_remove`), and remote SSH workspace setup.
     - `lib/symphony_elixir/path_safety.ex`: Path canonicalization utility validating workspace path containment inside root directories.
     - `lib/symphony_elixir/ssh.ex`: Remote SSH execution client.
   - **Agent Execution & Codex Protocol Domain**:
     - `lib/symphony_elixir/agent_runner.ex:1-204`: Agent runner executing multi-turn Codex runs (`run_codex_turns/5`) up to `agent.max_turns`.
     - `lib/symphony_elixir/prompt_builder.ex:1-65`: Solid template renderer generating turn prompts from issue attributes.
     - `lib/symphony_elixir/codex/app_server.ex:1-1099`: JSON-RPC 2.0 stdio protocol handler for Codex app-server stream.
     - `lib/symphony_elixir/codex/dynamic_tool.ex:1-210`: Implementation of client-side `linear_graphql` tool.
   - **Observability Surface Domain**:
     - `lib/symphony_elixir/status_dashboard.ex:1-1953`: Interactive terminal UI GenServer with ANSI formatting and sparkline throughput graphs.
     - `lib/symphony_elixir_web/controllers/observability_api_controller.ex`: JSON API controller exposing `/api/v1/state` and `/api/v1/:identifier`.
     - `lib/symphony_elixir_web/live/dashboard_live.ex`: LiveView real-time dashboard web interface.

---

## 2. Logic Chain

1. **From System Architecture to Domain Boundaries**:
   The investigation started by reading `SPEC.md` and `README.md`, which specify that Symphony operates as a scheduler daemon loading `WORKFLOW.md`, polling Linear, creating per-issue workspaces, running Codex app-server sessions, and presenting observability outputs.
2. **From Source Inspection to Business Categorization**:
   Inspecting `elixir/lib/symphony_elixir` revealed a strict 6-domain architectural hierarchy:
   - Configuration management is encapsulated in `Workflow` and `Config.Schema`.
   - Tracker communication is isolated in `Linear.Adapter` and `Linear.Issue`.
   - Process supervision, polling, concurrency control, and backoff retries are owned by `Orchestrator`.
   - File isolation and shell hooks are encapsulated in `Workspace` and `PathSafety`.
   - Subprocess RPC streaming, prompt interpolation, and dynamic tool execution are owned by `AgentRunner`, `PromptBuilder`, and `Codex.AppServer`.
   - Operational feedback is routed through `StatusDashboard`, `LogFile`, and `SymphonyElixirWeb`.
3. **From Data Models to State Machine Logic**:
   The `%Orchestrator.State{}` struct explicitly tracks issues across discrete state sets (`running`, `claimed`, `completed`, `blocked`, `retry_attempts`), enabling robust reconciliation whenever external Linear issue states change or workers exit.

---

## 3. Caveats

1. **Non-Elixir Implementations**: The repository contains `SPEC.md` (a language-agnostic specification) and `elixir/` (the prototype Elixir reference implementation). The analysis focuses primarily on the Elixir reference implementation as it is the sole active code tree present in the codebase.
2. **Third-Party External Services**: Live end-to-end functionality depends on external Linear API endpoints and a local/remote `codex app-server` binary, which were evaluated via static code inspection and unit tests rather than live network calls.

---

## 4. Conclusion

Symphony exhibits a modular, OTP-idiomatic architecture that cleanly segregates operational concerns into **6 Core Business Domains**:
1. Workflow & Policy Configuration
2. Issue Tracker Integration
3. Core Orchestration Engine
4. Workspace & Sandbox Management
5. Agent Execution & Codex Protocol
6. Observability & Web Dashboard

The codebase has been fully analyzed and documented in `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_2/analysis.md`.

---

## 5. Verification Method

To independently verify the observations and analysis:

1. **File Inspection**:
   - Inspect `analysis.md` in `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_2/analysis.md`.
   - Verify module structures against `elixir/lib/symphony_elixir/`.

2. **Test Suite Execution**:
   Run the project test suite using Mix inside the `elixir/` directory:
   ```bash
   cd /home/will/Projects/symphony/elixir
   mix test
   ```
   Specific domain tests can be executed individually:
   - `mix test test/symphony_elixir/orchestrator_status_test.exs` (Orchestrator domain)
   - `mix test test/symphony_elixir/workspace_and_config_test.exs` (Workspace & Config domains)
   - `mix test test/symphony_elixir/app_server_test.exs` (Codex protocol domain)
