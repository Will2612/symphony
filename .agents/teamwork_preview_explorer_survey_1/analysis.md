# Symphony Architecture & System Exploration Analysis

## 1. Executive Summary

**Symphony** is an autonomous coding agent orchestration service developed by OpenAI. It converts issue-tracker work items (primarily from Linear) into isolated, unattended implementation runs by spawning and managing coding agent sessions (Codex). 

The repository comprises:
1. **Language-Agnostic System Specification** (`SPEC.md`): Defines the 8 core functional components and protocol contracts for any language implementation.
2. **Elixir Reference Implementation** (`elixir/`): A production-grade Elixir 1.19 / Erlang OTP implementation using Phoenix 1.8, Phoenix LiveView 1.1, Bandit, Ecto schema validation, and JSON-RPC 2.0 stdio integration with Codex.
3. **Repository-Driven Workflow Contract** (`WORKFLOW.md`): Embedded configuration (YAML front-matter) and agent prompt templates (Liquid syntax) stored alongside project code.

---

## 2. Directory Structure & Layout

```
symphony/
├── .agents/                 # Multi-agent metadata and coordination directories
├── .codex/                  # Codex agent rules and default settings
├── .github/                 # CI/CD workflows and media assets
├── blog/                    # Promotional & launch announcements
├── docs/                    # Integration smoke tests
├── elixir/                  # Elixir Reference Implementation
│   ├── bin/                 # Output target directory for escript binary (`bin/symphony`)
│   ├── config/              # Application environment configs (config.exs, dev.exs, prod.exs, test.exs, runtime.exs)
│   ├── docs/                # Developer guides (logging.md, token_accounting.md)
│   ├── lib/                 # Elixir core source code
│   │   ├── mix/tasks/       # Custom Mix tasks (specs.check, pr_body.check, workspace.before_remove)
│   │   ├── symphony_elixir/ # Core domain logic modules
│   │   └── symphony_elixir_web/ # Phoenix web server, LiveView dashboard & REST API
│   ├── priv/                # Web dashboard static assets (CSS, JS)
│   ├── test/                # ExUnit test suite & fixtures (unit, integration, snapshot, Docker E2E)
│   ├── AGENTS.md            # Operational instructions for coding agents
│   ├── Makefile             # Build automation shortcuts
│   ├── README.md            # Elixir setup & usage documentation
│   ├── WORKFLOW.md          # Reference workflow file (Linear config & Liquid prompt)
│   ├── mix.exs              # Mix project configuration & dependencies
│   └── mix.lock             # Dependency lockfile
├── LICENSE                  # Apache License 2.0
├── NOTICE                   # Third-party notices
├── README.md                # Top-level project README
└── SPEC.md                  # Language-agnostic specification (8 components)
```

---

## 3. High-Level System Architecture

Symphony operates as a stateful, long-running Elixir OTP application centered around the `SymphonyElixir.Orchestrator` GenServer polling loop.

```mermaid
flowchart TD
    subgraph Tracker["Issue Tracker Layer"]
        Linear[Linear GraphQL API]
        MemTracker[Memory Tracker (Test)]
    end

    subgraph CLI["CLI / Entry Point"]
        Bin["bin/symphony (CLI)"]
    end

    subgraph OTP["OTP Application (SymphonyElixir.Application)"]
        Sup["SymphonyElixir.Supervisor"]
        PubSub["Phoenix.PubSub"]
        TaskSup["Task.Supervisor"]
        WFStore["SymphonyElixir.WorkflowStore"]
        Orch["SymphonyElixir.Orchestrator (GenServer)"]
        HTTP["SymphonyElixir.HttpServer (Bandit/Phoenix)"]
        Dash["SymphonyElixir.StatusDashboard"]
    end

    subgraph Worker["Worker Execution Layer"]
        Runner["SymphonyElixir.AgentRunner"]
        Prompt["SymphonyElixir.PromptBuilder"]
        WSpace["SymphonyElixir.Workspace"]
    end

    subgraph CodexIntegration["Codex AppServer Interface"]
        AppServer["Codex.AppServer (JSON-RPC 2.0 over Stdio/SSH)"]
        DynTool["Codex.DynamicTool (linear_graphql)"]
        CodexCLI["Codex CLI / Process"]
    end

    subgraph Observability["UI & Observability"]
        LiveView["DashboardLive (Web UI)"]
        RestAPI["ObservabilityApiController (REST API)"]
        TermUI["Terminal Status Bar"]
    end

    Bin -->|starts| OTP
    Sup --> PubSub
    Sup --> TaskSup
    Sup --> WFStore
    Sup --> Orch
    Sup --> HTTP
    Sup --> Dash

    Orch -->|polls active issues| Tracker
    Orch -->|dispatches work| TaskSup
    TaskSup -->|spawns| Runner

    Runner -->|resolves template| Prompt
    Runner -->|prepares workspace| WSpace
    Runner -->|starts session| AppServer

    AppServer <-->|stdio / JSON-RPC| CodexCLI
    AppServer <-->|executes tools| DynTool
    DynTool -->|GraphQL requests| Linear

    HTTP --> LiveView
    HTTP --> RestAPI
    Dash --> TermUI
```

---

## 4. Main Entry Points & Lifecycles

### 4.1 Escript CLI Entry Point (`SymphonyElixir.CLI`)
- **File**: `elixir/lib/symphony_elixir/cli.ex`
- **Main Function**: `SymphonyElixir.CLI.main/1` (Line 21)
- **Switches & Options**:
  - `--i-understand-that-this-will-be-running-without-the-usual-guardrails` (Required safety flag, Line 8, 105)
  - `--logs-root <path>` (Custom structured logs directory, Line 89)
  - `--port <port>` (HTTP observability dashboard port override, Line 151)
  - `[path-to-WORKFLOW.md]` (Optional positional argument; defaults to `./WORKFLOW.md`, Line 39)
- **Flow**:
  1. Validates CLI arguments and mandatory safety acknowledgment.
  2. Sets workflow file path (`SymphonyElixir.Workflow.set_workflow_file_path/1`).
  3. Boots `:symphony_elixir` OTP application via `Application.ensure_all_started/1`.
  4. Monitors `SymphonyElixir.Supervisor` process and waits for shutdown signal (`wait_for_shutdown/0`, Line 173).

### 4.2 OTP Application Entry Point (`SymphonyElixir.Application`)
- **File**: `elixir/lib/symphony_elixir.ex` (Line 15)
- **Callback**: `start/2` (Line 23)
- **Supervision Tree**:
  1. `Phoenix.PubSub` (`SymphonyElixir.PubSub`) — Event broadcasting for real-time LiveView UI updates.
  2. `Task.Supervisor` (`SymphonyElixir.TaskSupervisor`) — Supervison tree for spawned concurrent worker tasks (`AgentRunner`).
  3. `SymphonyElixir.WorkflowStore` — In-memory GenServer cache for parsed `WORKFLOW.md` data.
  4. `SymphonyElixir.Orchestrator` — Polling loop & worker dispatch state machine.
  5. `SymphonyElixir.HttpServer` — Phoenix Endpoint wrapper running Bandit web server for dashboard and REST observability API.
  6. `SymphonyElixir.StatusDashboard` — Terminal status line renderer.

---

## 5. Core Module Breakdown & Responsibilities

| Subsystem / Module | File Location | Key Responsibilities & Functions |
| --- | --- | --- |
| **Workflow Loader** (`SymphonyElixir.Workflow`) | `elixir/lib/symphony_elixir/workflow.ex` | Reads `WORKFLOW.md`, parses YAML front-matter and Liquid prompt body via `YamlElixir`. |
| **Config Validation** (`SymphonyElixir.Config.Schema`) | `elixir/lib/symphony_elixir/config/schema.ex` | Ecto schema for strict type validation of settings (`Tracker`, `Polling`, `Workspace`, `Hooks`, `Agent`, `Codex`, `Server`, `Worker`). |
| **Config Accessor** (`SymphonyElixir.Config`) | `elixir/lib/symphony_elixir/config.ex` | Provides typed getter functions (`settings/0`, `max_concurrent_agents_for_state/1`, `server_port/0`). |
| **Tracker Adapter Boundary** (`SymphonyElixir.Tracker`) | `elixir/lib/symphony_elixir/tracker.ex` | Behaviour contract defining issue fetching, state updates, comment creation. Delegates to `Linear.Adapter` or `Tracker.Memory`. |
| **Linear Client** (`SymphonyElixir.Linear.Client`) | `elixir/lib/symphony_elixir/linear/client.ex` | Sends GraphQL requests to Linear API endpoint using `Req`. |
| **Orchestrator** (`SymphonyElixir.Orchestrator`) | `elixir/lib/symphony_elixir/orchestrator.ex` | `GenServer` managing polling ticks, active running tasks, max concurrency limits, retry backoffs, Codex token accounting. |
| **Agent Runner** (`SymphonyElixir.AgentRunner`) | `elixir/lib/symphony_elixir/agent_runner.ex` | Task execution logic for a single issue: workspace setup, lifecycle hooks, Codex session turns, status updates. |
| **Codex AppServer Client** (`SymphonyElixir.Codex.AppServer`) | `elixir/lib/symphony_elixir/codex/app_server.ex` | JSON-RPC 2.0 stdio client interfacing with Codex CLI (or SSH remote host). Handles `initialize`, `thread/start`, `turn/start`. |
| **Dynamic Tool Executor** (`SymphonyElixir.Codex.DynamicTool`) | `elixir/lib/symphony_elixir/codex/dynamic_tool.ex` | Executes client-side tools requested by Codex turns (e.g. `linear_graphql`). |
| **Prompt Builder** (`SymphonyElixir.PromptBuilder`) | `elixir/lib/symphony_elixir/prompt_builder.ex` | Renders Liquid prompt templates with issue metadata, attempt numbers, and turn context using `Solid`. |
| **Workspace Manager** (`SymphonyElixir.Workspace`) | `elixir/lib/symphony_elixir/workspace.ex` | Manages per-issue directory creation, path safety checks (`PathSafety`), lifecycle hooks (`before_run`, `after_run`, `before_remove`), cleanup of terminal issues. |
| **HTTP Server** (`SymphonyElixir.HttpServer`) | `elixir/lib/symphony_elixir/http_server.ex` | Wraps `SymphonyElixirWeb.Endpoint` with Bandit server configuration and dynamic port selection. |
| **Web Router & REST API** (`SymphonyElixirWeb.Router`) | `elixir/lib/symphony_elixir_web/router.ex` | Exposes Phoenix LiveView (`/`), REST API (`/api/v1/state`, `/api/v1/refresh`, `/api/v1/:issue_identifier`), and static asset controllers. |
| **Terminal Dashboard** (`SymphonyElixir.StatusDashboard`) | `elixir/lib/symphony_elixir/status_dashboard.ex` | Renders real-time ANSI terminal UI with active issue states, queue counters, token totals, and rate limits. |

---

## 6. Build Infrastructure, Dependencies & Test Suite

### 6.1 Mix Project Configuration (`elixir/mix.exs`)
- **Elixir Requirement**: `~> 1.19`
- **Application Mod**: `{SymphonyElixir.Application, []}`
- **Escript Target**: `bin/symphony` (Main module: `SymphonyElixir.CLI`)
- **Key Dependencies**:
  - `phoenix` (`~> 1.8.0`) & `phoenix_live_view` (`~> 1.1.0`): Real-time web UI dashboard.
  - `bandit` (`~> 1.8`): HTTP/Websocket web server.
  - `req` (`~> 0.5`): HTTP client for Linear GraphQL API.
  - `jason` (`~> 1.4`): JSON parsing for JSON-RPC 2.0.
  - `yaml_elixir` (`~> 2.12`): YAML front-matter parser for `WORKFLOW.md`.
  - `solid` (`~> 1.2`): Liquid prompt templating engine.
  - `ecto` (`~> 3.13`): Configuration schema validation.
  - `credo` (`~> 1.7`) & `dialyxir` (`~> 1.4`): Static code quality & type checking.

### 6.2 Custom Mix Tasks
- `mix build`: Runs `escript.build` to generate `bin/symphony`.
- `mix specs.check`: Custom task (`lib/mix/tasks/specs.check.ex`) that enforces adjacent `@spec` annotations on all public functions in `lib/`.
- `mix pr_body.check`: Custom task (`lib/mix/tasks/pr_body.check.ex`) checking PR body compliance.
- `mix workspace.before_remove`: Custom lifecycle hook helper (`lib/mix/tasks/workspace.before_remove.ex`).

### 6.3 Test Infrastructure (`elixir/test/`)
- Unit & integration tests targeting all major modules (`core_test.exs`, `app_server_test.exs`, `workspace_and_config_test.exs`, `orchestrator_status_test.exs`).
- Snapshot testing via `test/support/snapshot_support.exs` and `fixtures/status_dashboard_snapshots/`.
- Docker-based Live E2E testing framework in `test/support/live_e2e_docker/`.

---

## 7. Conclusions & Strategic Observations

1. **Clean Separation of Policy and Mechanism**: System runtime settings, concurrency limits, lifecycle hooks, and agent prompts live entirely in `WORKFLOW.md`, while Symphony handles scheduling, workspace isolation, stdio protocol translation, and observability.
2. **High Resiliency**: State reconciliation relies on Linear issue states rather than a persistent database. Restarting Symphony cleanly re-queries Linear and inspects on-disk workspaces.
3. **Rich Observability**: Provides terminal status line UI, real-time Phoenix LiveView web dashboard, REST observability endpoints, and JSON structured logs.
