# Handoff Report — Explorer 1 (Architecture & Entry Points)

## 1. Observation

- **Root Directory Structure**:
  - `SPEC.md`: 2170 lines, language-agnostic specification defining 8 core system components.
  - `README.md`: Describes Symphony's mission and setup.
  - `elixir/`: Main Elixir reference implementation folder.

- **Elixir Project Manifest (`elixir/mix.exs`)**:
  - `app`: `:symphony_elixir`, `version`: `"0.1.0"`, `elixir`: `"~> 1.19"` (Lines 6-8).
  - Main CLI module: `SymphonyElixir.CLI` targeting binary output `bin/symphony` (Lines 93-95).
  - Application module: `{SymphonyElixir.Application, []}` (Line 58).
  - Custom aliases: `setup: ["deps.get"]`, `build: ["escript.build"]`, `lint: ["specs.check", "credo --strict"]` (Lines 84-87).
  - Dependencies include `bandit`, `phoenix`, `phoenix_live_view`, `req`, `jason`, `yaml_elixir`, `solid`, `ecto`, `credo`, `dialyxir`.

- **CLI Entry Point (`elixir/lib/symphony_elixir/cli.ex`)**:
  - Function: `SymphonyElixir.CLI.main/1` (Line 21).
  - Requires `--i-understand-that-this-will-be-running-without-the-usual-guardrails` switch (Line 8, 105).
  - Accepts optional `--logs-root`, `--port`, and `[path-to-WORKFLOW.md]` (Line 9, 34-47).
  - Boots application with `Application.ensure_all_started(:symphony_elixir)` (Line 85).

- **OTP Application Supervisor (`elixir/lib/symphony_elixir.ex`)**:
  - `SymphonyElixir.Application.start/2` (Line 23) starts a `:one_for_one` supervisor tree with children:
    1. `{Phoenix.PubSub, name: SymphonyElixir.PubSub}`
    2. `{Task.Supervisor, name: SymphonyElixir.TaskSupervisor}`
    3. `SymphonyElixir.WorkflowStore`
    4. `SymphonyElixir.Orchestrator`
    5. `SymphonyElixir.HttpServer`
    6. `SymphonyElixir.StatusDashboard`

- **Core Module Locations**:
  - `elixir/lib/symphony_elixir/orchestrator.ex`: Main `GenServer` polling state machine (Lines 1-1922).
  - `elixir/lib/symphony_elixir/workflow.ex` & `workflow_store.ex`: Parses YAML front-matter and Liquid prompt template from `WORKFLOW.md`.
  - `elixir/lib/symphony_elixir/config.ex` & `config/schema.ex`: Strict validation of configuration schema via Ecto.
  - `elixir/lib/symphony_elixir/tracker.ex` & `linear/`: Behavior for task tracking with Linear GraphQL adapter and memory mock adapter.
  - `elixir/lib/symphony_elixir/agent_runner.ex`: Worker process running individual issue turns under `Task.Supervisor`.
  - `elixir/lib/symphony_elixir/codex/app_server.ex` & `dynamic_tool.ex`: JSON-RPC 2.0 stdio integration with Codex CLI and dynamic tool execution (`linear_graphql`).
  - `elixir/lib/symphony_elixir/workspace.ex`: Per-issue workspace directory manager and lifecycle hook executor.
  - `elixir/lib/symphony_elixir_web/`: Phoenix Web dashboard (`DashboardLive`), REST observability API (`ObservabilityApiController`), static asset controllers, router (`router.ex`), endpoint (`endpoint.ex`).

---

## 2. Logic Chain

1. **Root Directory Examination**: Observing `SPEC.md` alongside `elixir/` confirms that `SPEC.md` defines the normative 8-component specification for Symphony, and `elixir/` is the active Elixir reference implementation.
2. **Build Configuration Examination**: `elixir/mix.exs` shows the project compiles to an escript executable (`bin/symphony`) via `mix build`, with `SymphonyElixir.CLI` as its main entry point and `SymphonyElixir.Application` as the OTP application callback.
3. **Entry Point Tracing**: Tracing `SymphonyElixir.CLI.main/1` -> `Application.ensure_all_started(:symphony_elixir)` -> `SymphonyElixir.Application.start/2` confirms that booting Symphony initializes a centralized supervisor tree (`SymphonyElixir.Supervisor`).
4. **Supervisor Child Tracing**: Inspecting child specifications shows the system architecture relies on:
   - `SymphonyElixir.PubSub` for event broadcasting.
   - `SymphonyElixir.TaskSupervisor` for isolated, async worker execution (`AgentRunner`).
   - `SymphonyElixir.WorkflowStore` for caching parsed `WORKFLOW.md` settings.
   - `SymphonyElixir.Orchestrator` for handling polling ticks, concurrency limits, and retry queues.
   - `SymphonyElixir.HttpServer` for hosting Phoenix LiveView (`/`) and REST API (`/api/v1/*`).
   - `SymphonyElixir.StatusDashboard` for ANSI terminal progress lines.
5. **Codex Protocol Tracing**: Inspecting `Codex.AppServer` and `Codex.DynamicTool` reveals that Codex sessions communicate via JSON-RPC 2.0 over stdio (or SSH stdio), with `linear_graphql` exposed as a client-side dynamic tool.

---

## 3. Caveats

- **External Integrations**: Deep runtime testing of live Linear GraphQL calls or live Codex CLI execution was not conducted in this read-only investigation turn.
- **Remote SSH Worker Verification**: `SSH` worker host handling in `AgentRunner` and `Workspace` was analyzed structurally from code; remote SSH infrastructure was not executed or tested.

---

## 4. Conclusion

Symphony is a modular, OTP-structured Elixir daemon application designed for autonomous coding agent orchestration. It cleanly separates workflow policy (`WORKFLOW.md`) from scheduling mechanics (`SymphonyElixir.Orchestrator`), workspace management (`SymphonyElixir.Workspace`), agent protocol communication (`Codex.AppServer`), and real-time observability (`SymphonyElixirWeb`). The codebase is fully explored and documented in `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_1/analysis.md`.

---

## 5. Verification Method

1. **Inspect Analysis Report**:
   - `view_file` on `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_1/analysis.md`.
2. **Verify Mix Alias and Compilation (Dry Run)**:
   - Run `mix help` or `mix specs.check` inside `/home/will/Projects/symphony/elixir/` (if dependencies are compiled).
3. **Inspect Core Files**:
   - Entry points: `elixir/lib/symphony_elixir/cli.ex` and `elixir/lib/symphony_elixir.ex`.
   - Orchestrator: `elixir/lib/symphony_elixir/orchestrator.ex`.
   - Router: `elixir/lib/symphony_elixir_web/router.ex`.
