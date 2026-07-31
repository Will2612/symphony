# Symphony Architecture Analysis — Core Business Domains & Logic

## Executive Summary

**Symphony** is an autonomous coding-agent orchestrator service designed to convert project issue tracker items (Linear) into isolated, repeatable, autonomous software implementation runs. Rather than requiring human engineers to supervise coding agent threads manually, Symphony acts as a scheduler/runner daemon that polls the issue tracker, provisions isolated per-issue workspace sandboxes, executes Codex app-server agent turns, handles multi-turn continuation, retries transient failures with exponential backoff, enforces path safety, and exposes real-time terminal/web observability surfaces.

This document provides a comprehensive structural breakdown of Symphony's core business domains, data models, key services, and business logic modules based on an extensive survey of the codebase (`/home/will/Projects/symphony`).

---

## 1. Domain Map Overview

Symphony's architecture is organized into **6 Core Business Domains**:

```
+---------------------------------------------------------------------------------------------------+
|                                       PROJECT SYMPHONY                                            |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  1. Workflow & Policy Configuration        2. Issue Tracker Integration                           |
|     - WORKFLOW.md Parser                      - Linear GraphQL Client / Adapter                   |
|     - Config Schema & Validation              - Issue Entity & Normalizer                         |
|     - WorkflowStore GenServer                 - Tracker Memory Mock                               |
|                                                                                                   |
|  3. Core Orchestration Engine              4. Workspace & Sandbox Management                      |
|     - Polling Loop & Tick Timer               - Workspace Creator & Hook Runner                   |
|     - State Machine (Running/Blocked/etc)     - Path Safety & Directory Isolation                 |
|     - Concurrency & Dispatch Logic            - Local & Remote (SSH) Worker Abstraction           |
|                                                                                                   |
|  5. Agent Execution & Codex Protocol       6. Observability & Monitoring Surface                  |
|     - Prompt Builder (Solid/Liquid)           - Status Dashboard (Terminal UI)                    |
|     - Codex AppServer JSON-RPC Client         - Phoenix LiveView & REST API (/api/v1)            |
|     - Dynamic Tool (linear_graphql)           - Structured Session Logging                        |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Core Business Domains & Module Catalog

### Domain 1: Workflow & Policy Configuration Domain

* **Module Path**: `lib/symphony_elixir/workflow.ex`, `lib/symphony_elixir/workflow_store.ex`, `lib/symphony_elixir/config.ex`, `lib/symphony_elixir/config/schema.ex`
* **Primary Responsibility**: Loads, validates, parses, and maintains runtime workflow policies defined in repo-level `WORKFLOW.md` files. Decouples prompt engineering and scheduler settings from application code.

#### Key Component Responsibilities:
* `SymphonyElixir.Workflow`: File loader that splits YAML front matter from Markdown prompt templates and parses YAML content into Elixir maps.
* `SymphonyElixir.WorkflowStore`: OTP GenServer storing the active loaded workflow state in memory and supporting live reloading on file updates.
* `SymphonyElixir.Config.Schema`: Ecto embedded schemas specifying configuration validation, default fallbacks, secret resolution (`$LINEAR_API_KEY`), path expansion (`$SYMPHONY_WORKSPACE_ROOT`), state limits, and turn sandbox policies.
* `SymphonyElixir.Config`: Public API providing typed configuration accessors (`Config.settings!()`) and validation (`Config.validate!()`).

#### Primary Data Models:

```elixir
# Workflow Configuration Schema Struct (derived from WORKFLOW.md front matter)
%SymphonyElixir.Config.Schema{
  tracker: %Tracker{
    kind: String.t(),            # e.g., "linear"
    endpoint: String.t(),        # default: "https://api.linear.app/graphql"
    api_key: String.t(),         # resolved from $LINEAR_API_KEY
    project_slug: String.t(),    # target project slug
    assignee: String.t() | nil,  # filter by assignee
    active_states: [String.t()], # default: ["Todo", "In Progress"]
    terminal_states: [String.t()]# default: ["Closed", "Cancelled", "Canceled", "Duplicate", "Done"]
  },
  polling: %Polling{
    interval_ms: integer()       # default: 30_000 (30 sec)
  },
  workspace: %Workspace{
    root: String.t()             # absolute workspace root path
  },
  worker: %Worker{
    ssh_hosts: [String.t()],    # remote SSH worker nodes
    max_concurrent_agents_per_host: integer()
  },
  agent: %Agent{
    max_concurrent_agents: integer(),          # default: 10
    max_turns: integer(),                      # default: 20
    max_retry_backoff_ms: integer(),           # default: 300_000 (5 min)
    max_concurrent_agents_by_state: map()       # per-state concurrency overrides
  },
  codex: %Codex{
    command: String.t(),                        # default: "codex app-server"
    approval_policy: String.t() | map(),        # rejection/approval rules
    thread_sandbox: String.t(),                 # e.g., "workspace-write"
    turn_sandbox_policy: map(),                 # sandbox restrictions map
    turn_timeout_ms: integer(),                 # default: 3_600_000 (1 hour)
    read_timeout_ms: integer(),                 # default: 5_000 (5 sec)
    stall_timeout_ms: integer()                 # default: 300_000 (5 min)
  },
  hooks: %Hooks{
    after_create: String.t() | nil,             # bootstrap script (e.g. git clone)
    before_run: String.t() | nil,
    after_run: String.t() | nil,
    before_remove: String.t() | nil,
    timeout_ms: integer()                       # default: 60_000 (1 min)
  },
  observability: %Observability{
    dashboard_enabled: boolean(), refresh_ms: integer(), render_interval_ms: integer()
  },
  server: %Server{port: integer() | nil, host: String.t()}
}
```

---

### Domain 2: Issue Tracker Integration Domain

* **Module Path**: `lib/symphony_elixir/linear/issue.ex`, `lib/symphony_elixir/linear/client.ex`, `lib/symphony_elixir/linear/adapter.ex`, `lib/symphony_elixir/tracker.ex`, `lib/symphony_elixir/tracker/memory.ex`
* **Primary Responsibility**: Abstracts ticket tracker interactions (Linear GraphQL API), queries active candidate issues, refreshes issue states for running/blocked reconciliation, and normalizes external data payloads into standard domain structs.

#### Key Component Responsibilities:
* `SymphonyElixir.Tracker`: Elixir Behaviour contract establishing standard data fetch interface (`fetch_candidate_issues/0`, `fetch_issue_states_by_ids/1`, `fetch_terminal_issues/0`).
* `SymphonyElixir.Linear.Client`: Finch-based HTTP GraphQL client executing authenticated requests against Linear's GraphQL API endpoint.
* `SymphonyElixir.Linear.Adapter`: Translates Linear GraphQL queries and mutations into normalized Symphony structs.
* `SymphonyElixir.Linear.Issue`: Domain model struct representing an issue ticket.
* `SymphonyElixir.Tracker.Memory`: In-memory mock tracker store used for deterministic testing and snapshot validation.

#### Primary Data Models:

```elixir
# Normalized Issue Domain Model
%SymphonyElixir.Linear.Issue{
  id: String.t(),                # Internal stable tracker ID (e.g. UUID)
  identifier: String.t(),        # Human-readable ticket key (e.g. "FEAT-101")
  title: String.t(),             # Issue title
  description: String.t() | nil, # Full issue body/description
  priority: integer() | nil,     # Priority score (lower numbers = higher priority)
  state: String.t(),             # Tracker state name (e.g. "In Progress", "Rework")
  branch_name: String.t() | nil, # Git branch name from tracker
  url: String.t() | nil,         # Web URL of the ticket
  assignee_id: String.t() | nil, # Assignee user ID
  blocked_by: [map()],           # Blocker issue references
  labels: [String.t()],          # Array of normalized label names
  assigned_to_worker: boolean(), # Filtering flag for worker routing
  created_at: DateTime.t(),
  updated_at: DateTime.t()
}
```

---

### Domain 3: Core Orchestration Engine Domain

* **Module Path**: `lib/symphony_elixir/orchestrator.ex`, `lib/symphony_elixir.ex`, `lib/symphony_elixir/status_dashboard.ex`
* **Primary Responsibility**: Acts as the central coordination brain and process scheduler. Polling issue tracker on scheduled ticks, sorting candidate work, managing concurrency pools, tracking agent process PIDs (`Task.Supervisor`), reconciling state when tickets move to non-active/terminal states, managing backoff retries, and recording token consumption metrics.

#### Key Component Responsibilities:
* `SymphonyElixir.Orchestrator`: Primary GenServer process driving system state transitions:
  1. **Poll Tick Loop**: Fires periodically (`polling.interval_ms`), querying `Tracker.fetch_candidate_issues()`.
  2. **Candidate Selection & Concurrency Bounding**: Sorts candidate issues by priority and creation time, checks global (`max_concurrent_agents`) and per-state limits (`max_concurrent_agents_by_state`), assigns worker hosts.
  3. **Agent Task Dispatch**: Spawns asynchronous tasks under `Task.Supervisor` running `AgentRunner.run/3`.
  4. **State Machine Management**: Tracks issues across states (`running`, `claimed`, `completed`, `blocked`, `retry_attempts`).
  5. **Reconciliation**: Periodically queries Linear for active/blocked issues (`reconcile_running_issues`, `reconcile_blocked_issues`). Stops active agents if ticket is moved to terminal state, closed, or reassigned.
  6. **Exponential Backoff**: Calculates retry delay using binary bit-shifting exponential backoff (`delay = min(base_ms * 2^(attempt - 1), max_backoff)`).

#### Primary Data Models:

```elixir
# Orchestrator Internal State Machine
%SymphonyElixir.Orchestrator.State{
  poll_interval_ms: integer(),
  max_concurrent_agents: integer(),
  next_poll_due_at_ms: integer() | nil,
  poll_check_in_progress: boolean(),
  running: %{
    issue_id => %{
      issue_id: String.t(),
      identifier: String.t(),
      state: String.t(),
      pid: pid(),
      ref: reference(),
      started_at_ms: integer(),
      worker_host: String.t() | nil,
      workspace_path: String.t() | nil,
      session_id: String.t() | nil,
      last_reported_input_tokens: integer(),
      last_reported_output_tokens: integer(),
      last_reported_total_tokens: integer()
    }
  },
  claimed: MapSet.t(),            # Set of claimed issue IDs
  completed: MapSet.t(),          # Set of completed issue IDs
  blocked: %{
    issue_id => %{
      issue_id: String.t(),
      identifier: String.t(),
      state: String.t(),
      blocked_at_ms: integer(),
      reason: String.t()
    }
  },
  retry_attempts: %{
    issue_id => %{
      issue_id: String.t(),
      identifier: String.t(),
      attempt: integer(),
      due_at_ms: integer(),
      delay_type: :failure | :continuation,
      error: String.t() | nil
    }
  },
  codex_totals: %{
    input_tokens: integer(), output_tokens: integer(), total_tokens: integer(), seconds_running: integer()
  },
  codex_rate_limits: map() | nil
}
```

---

### Domain 4: Workspace & Sandbox Management Domain

* **Module Path**: `lib/symphony_elixir/workspace.ex`, `lib/symphony_elixir/path_safety.ex`, `lib/symphony_elixir/ssh.ex`
* **Primary Responsibility**: Dynamically provisions per-issue directory environments, executes lifecycle hooks (`after_create`, `before_run`, `after_run`, `before_remove`), enforces strict path canonicalization to prevent path traversal security vulnerabilities, and manages remote execution over SSH.

#### Key Component Responsibilities:
* `SymphonyElixir.Workspace`: Handles workspace creation (`create_for_issue/2`), directory structure initialization, lifecycle hook invocation (`run_hook/5`), and terminal workspace teardown (`remove/2`).
* `SymphonyElixir.PathSafety`: Security layer ensuring workspace paths resolve strictly within designated `workspace.root` through canonical realpath evaluation, preventing symlink traversal or escape attacks.
* `SymphonyElixir.SSH`: Wrapper for remote worker execution via SSH commands and ports when running on multi-node SSH worker pools.

#### Lifecycle Hooks Flow:
1. `after_create`: Executed only when a new workspace directory is created for the first time (e.g. `git clone <repo> .`).
2. `before_run`: Executed prior to launching every Codex agent session turn.
3. `after_run`: Executed after completing a Codex agent session turn (runs regardless of success or failure).
4. `before_remove`: Executed before a workspace directory is permanently removed upon issue completion/closure.

---

### Domain 5: Agent Execution & Codex Protocol Domain

* **Module Path**: `lib/symphony_elixir/agent_runner.ex`, `lib/symphony_elixir/prompt_builder.ex`, `lib/symphony_elixir/codex/app_server.ex`, `lib/symphony_elixir/codex/dynamic_tool.ex`
* **Primary Responsibility**: Drives coding agent subprocesses, constructs dynamic system prompts using Liquid/Solid templates, manages JSON-RPC 2.0 stdio stream communication with `codex app-server`, enforces turn limits, and services client-side dynamic tool calls.

#### Key Component Responsibilities:
* `SymphonyElixir.PromptBuilder`: Parses and renders Liquid templates in `WORKFLOW.md` using the `Solid` library, injecting issue fields (`identifier`, `title`, `description`, `labels`, `attempt`).
* `SymphonyElixir.AgentRunner`: Controls the lifecycle of an individual agent execution run:
  - Invokes workspace creation & `before_run` hook.
  - Spawns Codex session via `AppServer.start_session/2`.
  - Runs turns sequentially (`do_run_codex_turns/8`) up to `agent.max_turns`.
  - Performs continuation checks with tracker (`continue_with_issue?/2`).
* `SymphonyElixir.Codex.AppServer`: Low-level JSON-RPC 2.0 stdio protocol driver:
  - Sends RPC requests: `initialize`, `thread/start`, `turn/start`.
  - Handles notifications: streaming agent text/reasoning deltas, token count metrics, rate limit status.
  - Serves incoming requests: `approval/request` (auto-rejected or evaluated against policy), `mcp/elicit`, `tool/call`.
* `SymphonyElixir.Codex.DynamicTool`: Exposes in-process `linear_graphql` tool allowing Codex agents inside workspace sessions to query/update Linear issue statuses or post comments directly via GraphQL.

---

### Domain 6: Observability & Web Dashboard Domain

* **Module Path**: `lib/symphony_elixir/status_dashboard.ex`, `lib/symphony_elixir/log_file.ex`, `lib/symphony_elixir/http_server.ex`, `lib/symphony_elixir_web/*`
* **Primary Responsibility**: Delivers real-time operational visibility into orchestrator state, active runs, token burn rates, backoff retry queues, and structured log sinks across both CLI terminal UI and web dashboard surfaces.

#### Key Component Responsibilities:
* `SymphonyElixir.StatusDashboard`: GenServer rendering rich terminal UI dashboard featuring ANSI color coding, sparklines (`▁▂▃▄▅▆▇█`), active worker metrics, token totals, and throughput rate graphs (tokens/sec).
* `SymphonyElixir.LogFile`: Configures structured file logger sinking session logs to `log/symphony.log` and per-issue session logs.
* `SymphonyElixir.HttpServer`: Bandit-powered HTTP server hosting Phoenix web stack.
* `SymphonyElixirWeb.Endpoint` & `Router`: Exposes:
  - `/`: Real-time Phoenix LiveView interactive status dashboard (`DashboardLive`).
  - `/api/v1/state`: Full JSON snapshot of runtime state (`ObservabilityApiController`).
  - `/api/v1/:identifier`: Detailed status JSON for a specific issue key.
  - `/api/v1/refresh`: Manual poll trigger endpoint.
* `SymphonyElixirWeb.ObservabilityPubSub`: Phoenix PubSub topic broadcasting snapshot updates to connected LiveView clients whenever orchestrator state changes.

---

## 3. End-to-End Orchestration Workflow Logic

The complete lifecycle of work execution in Symphony follows this deterministic workflow:

```
 [ Linear Tracker ]
        |
        | 1. Poll candidate issues (active states, assigned to project/worker)
        v
 [ Orchestrator ]
        |
        | 2. Check available slots & per-state limits
        | 3. Sort by priority (asc) & creation date (asc)
        v
 [ Workspace Manager ]
        |
        | 4. Canonicalize path & create directory
        | 5. Run `after_create` hook (e.g. git clone) if new
        | 6. Run `before_run` hook
        v
 [ Agent Runner & Codex AppServer ]
        |
        | 7. Render prompt using Solid template + issue data
        | 8. Launch `codex app-server` via JSON-RPC stdio
        | 9. Execute turn (agent edits code, runs tools, linear_graphql)
        | 10. Stream tokens, reasoning deltas, and state updates to Orchestrator
        v
 [ Continuation / Completion ]
        |
        +---> If Issue is STILL Active & Turn < max_turns: Run Continuation Turn
        +---> If Issue is BLOCKED (requires input/approval): Move to Blocked State
        +---> If Agent FAILS / Exits with Error: Schedule Exponential Backoff Retry
        +---> If Issue moves to TERMINAL State: Stop Agent & Clean Up Workspace
```

---

## 4. Key Architectural Patterns & Characteristics

1. **BEAM / OTP Supervision & Process Isolation**:
   Every agent run executes inside a separate process supervised by `Task.Supervisor`. Crashes or timeouts in an individual Codex session do not affect the main orchestrator or other running agents.

2. **Stateless Scheduler with External Source of Truth**:
   Symphony does not rely on a persistent database. Scheduler state is maintained in-memory (`Orchestrator.State`). On restart, state is naturally reconstructed by querying Linear and inspecting filesystem workspaces.

3. **In-Repo Policy Contract (`WORKFLOW.md`)**:
   System prompt templates, tracker configs, concurrency caps, approval policies, and sandbox rules are version-controlled alongside application code.

4. **Multi-Node SSH Scaling**:
   Symphony supports dispatching agent runs across SSH worker hosts (`worker.ssh_hosts`), managing workspace creation and command execution transparently over remote SSH channels.

5. **Multi-Surface Observability**:
   Unified state updates feed simultaneously into CLI terminal UI displays, Phoenix LiveView web interfaces, REST APIs, and structured log files.

---

## 5. Verification Matrix & Code Locations

| Domain | Key Files | Verification Method |
|---|---|---|
| **Workflow & Policy** | `lib/symphony_elixir/workflow.ex`<br>`lib/symphony_elixir/config/schema.ex` | `mix test test/symphony_elixir/workspace_and_config_test.exs` |
| **Tracker Integration** | `lib/symphony_elixir/linear/issue.ex`<br>`lib/symphony_elixir/linear/client.ex` | `mix test test/symphony_elixir/core_test.exs` |
| **Orchestration Engine** | `lib/symphony_elixir/orchestrator.ex` | `mix test test/symphony_elixir/orchestrator_status_test.exs` |
| **Workspace & Path Safety** | `lib/symphony_elixir/workspace.ex`<br>`lib/symphony_elixir/path_safety.ex` | `mix test test/symphony_elixir/workspace_and_config_test.exs` |
| **Agent Execution & Codex** | `lib/symphony_elixir/agent_runner.ex`<br>`lib/symphony_elixir/codex/app_server.ex` | `mix test test/symphony_elixir/app_server_test.exs` |
| **Observability Surface** | `lib/symphony_elixir/status_dashboard.ex`<br>`lib/symphony_elixir_web/` | `mix test test/symphony_elixir/status_dashboard_snapshot_test.exs` |

