# Workflow Specification & Configuration System

This document provides a comprehensive technical guide to the **Workflow & Configuration System** in Symphony. It details the specification of `WORKFLOW.md`, the parsing and validation mechanics executed by `SymphonyElixir.Workflow` and `SymphonyElixir.Config.Schema`, the in-memory hot-reloading GenServer `SymphonyElixir.WorkflowStore`, environment variable indirection, and prompt compilation using Liquid templates via `SymphonyElixir.PromptBuilder`.

---

## 1. Overview & Architecture Summary

Symphony follows a **declarative, repository-driven configuration model**. Instead of requiring external databases or centralized administration dashboards, each Symphony installation reads its operational parameters and agent prompt instructions directly from a single repository file: `WORKFLOW.md`.

### Core Architectural Principles
1. **Unified Specification File (`WORKFLOW.md`)**: A single multi-part Markdown document containing both structured operational metadata (YAML front-matter) and agent instructions (Liquid prompt body).
2. **Strict Type & Schema Validation**: Driven by `Ecto.Schema` embedded structs, ensuring malformed or unsafe workflow files are rejected before execution.
3. **Hot-Reloading In-Memory Caching**: Managed by `SymphonyElixir.WorkflowStore`, a `GenServer` that polls the file system every 1,000 milliseconds for changes using modification timestamps, byte size, and Erlang term hashes (`phash2`).
4. **Environment Variable Indirection**: Sensitive tokens (such as API keys) and environment-dependent paths can be specified as indirection strings (e.g., `$LINEAR_API_KEY`, `$SYMPHONY_WORKSPACE_ROOT`) which are dynamically resolved at runtime.
5. **Fault-Tolerant Fallback**: If an edited `WORKFLOW.md` contains syntax errors or invalid schema attributes, the system retains the last known good configuration in memory and logs diagnostic errors without crashing the service.

---

## 2. `WORKFLOW.md` File Specification

A valid `WORKFLOW.md` file consists of two primary sections separated by Markdown YAML front-matter delimiters (`---`).

```markdown
---
# Section 1: Front-Matter YAML Configuration
tracker:
  kind: linear
  project_slug: "my-project-slug"
  active_states:
    - Todo
    - In Progress
polling:
  interval_ms: 5000
agent:
  max_concurrent_agents: 5
---

<!-- Section 2: Agent Prompt Template (Liquid Syntax) -->
You are working on Linear issue {{ issue.identifier }}.
Title: {{ issue.title }}

Description:
{% if issue.description %}
{{ issue.description }}
{% else %}
No description provided.
{% endif %}
```

### 2.1 Front-Matter YAML Schema Fields

The front-matter section decodes into an Elixir map that maps directly to nested sub-schemas within `SymphonyElixir.Config.Schema`:

| Root Key | Field Name | Type | Default Value | Description / Validation |
| :--- | :--- | :--- | :--- | :--- |
| `tracker` | `kind` | `String.t()` | `nil` | Tracker backend (`"linear"` or `"memory"`). |
| | `endpoint` | `String.t()` | `"https://api.linear.app/graphql"` | GraphQL API endpoint URL for Linear. |
| | `api_key` | `String.t()` | `nil` | API token or env var reference (`$LINEAR_API_KEY`). |
| | `project_slug` | `String.t()` | `nil` | Linear project identifier/slug. |
| | `assignee` | `String.t()` | `nil` | User ID / email filter or env var (`$LINEAR_ASSIGNEE`). |
| | `active_states` | `list(String.t())` | `["Todo", "In Progress"]` | Issue states considered active for worker scheduling. |
| | `terminal_states` | `list(String.t())` | `["Closed", "Cancelled", "Canceled", "Duplicate", "Done"]` | Issue states that mark completion or termination. |
| `polling` | `interval_ms` | `pos_integer()` | `30000` | Polling interval in milliseconds (must be > 0). |
| `workspace` | `root` | `String.t()` | `System.tmp_dir()/symphony_workspaces` | Directory path or env reference for issue workspaces. |
| `worker` | `ssh_hosts` | `list(String.t())` | `[]` | List of SSH host strings for distributed agent execution. |
| | `max_concurrent_agents_per_host` | `pos_integer()` | `nil` | Maximum agents allowed to run per remote host. |
| `agent` | `max_concurrent_agents` | `pos_integer()` | `10` | Global concurrency cap for active agent runs. |
| | `max_turns` | `pos_integer()` | `20` | Maximum turn iterations permitted per issue session. |
| | `max_retry_backoff_ms` | `pos_integer()` | `300000` | Upper limit (5 mins) for exponential backoff retries. |
| | `max_concurrent_agents_by_state` | `map()` | `%{}` | Map of state names (e.g. `{"in progress" => 3}`) to limit limits. |
| `codex` | `command` | `String.t()` | `"codex app-server"` | Command line invocation to spawn the Codex app-server. |
| | `approval_policy` | `String.t() \| map()` | `%{ "reject" => %{ ... } }` | Approval policy map or string (`"never"`, `"on-request"`). |
| | `thread_sandbox` | `String.t()` | `"workspace-write"` | Codex sandbox policy (`"workspace-write"`, `"read-only"`). |
| | `turn_sandbox_policy` | `map()` | Auto-generated | Explicit turn sandbox policy overrides. |
| | `turn_timeout_ms` | `pos_integer()` | `3600000` | Turn execution timeout (1 hour default). |
| | `read_timeout_ms` | `pos_integer()` | `5000` | Stdio read timeout in milliseconds. |
| | `stall_timeout_ms` | `non_neg_integer()` | `300000` | Timeout for detecting stuck or silent turns (5 mins). |
| `hooks` | `after_create` | `String.t()` | `nil` | Shell command executed immediately after workspace creation. |
| | `before_run` | `String.t()` | `nil` | Shell command executed before an agent turn begins. |
| | `after_run` | `String.t()` | `nil` | Shell command executed after an agent turn finishes. |
| | `before_remove` | `String.t()` | `nil` | Shell command executed before workspace deletion. |
| | `timeout_ms` | `pos_integer()` | `60000` | Execution timeout for lifecycle hook scripts. |
| `observability` | `dashboard_enabled` | `boolean()` | `true` | Enables or disables the Phoenix LiveView dashboard. |
| | `refresh_ms` | `pos_integer()` | `1000` | Web UI auto-refresh update frequency. |
| | `render_interval_ms` | `pos_integer()` | `16` | UI rendering throttle (~60 FPS). |
| `server` | `port` | `non_neg_integer()` | `nil` | HTTP web server port binding (0 for random assigned port). |
| | `host` | `String.t()` | `"127.0.0.1"` | IP address interface binding. |

### 2.2 Prompt Body Template & Liquid Context

The content located below the second `---` delimiter serves as a **Liquid template** (parsed via the `Solid` library). When an agent session is initialized by `SymphonyElixir.AgentRunner`, the prompt template is rendered with runtime variables.

#### Available Template Variables
- `issue`: Map representing the target issue metadata:
  - `issue.identifier`: Issue key string (e.g. `"MT-42"`).
  - `issue.title`: Title of the issue.
  - `issue.description`: Markdown body of the issue (or `nil` if omitted).
  - `issue.state`: Current status name (e.g. `"In Progress"`).
  - `issue.labels`: List of label strings attached to the issue.
  - `issue.url`: Canonical HTTP URL to the issue.
  - `issue.priority`: Integer priority level (1 = Urgent, 2 = High, 3 = Normal, 4 = Low, 0 = None).
  - `issue.createdAt`: ISO-8601 formatted creation timestamp.
  - `issue.updatedAt`: ISO-8601 formatted update timestamp.
- `attempt`: Integer (1-indexed) representing the current attempt count if the session is a retry loop.

#### Workpad Protocol in Standard Prompts
The standard `WORKFLOW.md` prompt establishes a mandatory operational protocol for agents:
1. **Single Scratchpad Comment (`## Codex Workpad`)**: Agents must create and continuously update a single persistent Linear comment starting with `## Codex Workpad` rather than posting multiple updates.
2. **Environment Stamp**: The workpad must log environment context in a code block: `<hostname>:<abs-path>@<short-sha>`.
3. **Execution Routing**: Routes actions strictly according to state transitions (`Todo` -> `In Progress` -> `Human Review` -> `Merging` -> `Done`).

---

## 3. Workflow File Parsing (`SymphonyElixir.Workflow`)

The `SymphonyElixir.Workflow` module provides functions to locate, read, and parse `WORKFLOW.md`.

```mermaid
flowchart TD
    Start[Call Workflow.current / load] --> ResolvePath[Resolve Workflow File Path]
    ResolvePath --> ReadFile{File.read path}
    ReadFile -- Error --> ErrMissing[Return error: missing_workflow_file]
    ReadFile -- OK content --> Split[split_front_matter content]
    Split --> ExtractYAML[Extract lines between initial --- and second ---]
    Split --> ExtractPrompt[Extract remaining lines as prompt body]
    ExtractYAML --> ParseYAML{YamlElixir.read_from_string}
    ParseYAML -- Error --> ErrYAML[Return error: workflow_parse_error]
    ParseYAML -- OK map --> ConstructResult[Construct workflow map]
    ConstructResult --> Return[Return {:ok, %{config: map, prompt: str, prompt_template: str}}]
```

### 3.1 Path Resolution Logic
The file path is determined dynamically:
```elixir
def workflow_file_path do
  Application.get_env(:symphony_elixir, :workflow_file_path) ||
    Path.join(File.cwd!(), "WORKFLOW.md")
end
```
When `SymphonyElixir.Workflow.set_workflow_file_path/1` is invoked, it updates the application environment key `:workflow_file_path` and notifies `SymphonyElixir.WorkflowStore` to perform an immediate reload.

### 3.2 Splitting & Parsing Mechanics
Parsing is executed in three stages:
1. `split_front_matter/1`: Uses regex `~r/\R/` (to correctly handle Linux `\n` and Windows `\r\n` line endings) to split file lines.
2. YAML Decoding: Converts front-matter lines into a YAML string and decodes it via `YamlElixir.read_from_string/1`. If the front-matter is empty, it defaults to `%{}`, but if YAML decodes to a non-map structure (such as a plain scalar or array), it returns `{:error, :workflow_front_matter_not_a_map}`.
3. Prompt Template Normalization: Joins lines after the second `---` and trims whitespace.

---

## 4. In-Memory Store & Hot-Reloading (`SymphonyElixir.WorkflowStore`)

`SymphonyElixir.WorkflowStore` is an OTP `GenServer` registered under its module name. It caches the parsed workflow in memory so that frequent read access (e.g. during orchestrator polling ticks) avoids repeated file I/O operations.

### 4.1 State & File Stamp Structure
The GenServer state is defined as:
```elixir
defmodule State do
  defstruct [:path, :stamp, :workflow]
end
```
The file fingerprint (`stamp`) is a 3-tuple computed via:
```elixir
defp current_stamp(path) do
  with {:ok, stat} <- File.stat(path, time: :posix),
       {:ok, content} <- File.read(path) do
    {:ok, {stat.mtime, stat.size, :erlang.phash2(content)}}
  end
end
```
By combining modification time (`mtime`), byte size (`size`), and the Erlang term hash (`phash2(content)`), the system detects content edits even when file modification timestamps remain identical across quick consecutive writes.

### 4.2 Periodic Polling & Fault-Tolerant Hot Reloading
- **Polling Loop**: Every 1,000 ms (`@poll_interval_ms`), the GenServer receives a `:poll` info message and schedules the next timer.
- **Reload Validation**:
  - If the path or stamp matches the stored state, no operation occurs.
  - If the stamp changes, `Workflow.load(path)` is invoked.
  - If parsing fails (e.g. invalid syntax written during an active edit), `WorkflowStore` logs an error via `Logger.error/1` and **retains the previous valid workflow state in memory**:
  ```elixir
  defp log_reload_error(path, reason) do
    Logger.error("Failed to reload workflow path=#{path} reason=#{inspect(reason)}; keeping last known good configuration")
  end
  ```

---

## 5. Ecto Configuration Validation (`SymphonyElixir.Config.Schema`)

Once raw YAML is parsed into a Map, `SymphonyElixir.Config.Schema.parse/1` validates types, normalizes keys, inserts defaults, and transforms the map into an `%Ecto.Changeset{}`.

```mermaid
classDiagram
    class ConfigSchema {
      +Tracker tracker
      +Polling polling
      +Workspace workspace
      +Worker worker
      +Agent agent
      +Codex codex
      +Hooks hooks
      +Observability observability
      +Server server
      +parse(map) {:ok, Schema.t()}
    }

    class Tracker {
      +String kind
      +String endpoint
      +String api_key
      +String project_slug
      +String assignee
      +List~String~ active_states
      +List~String~ terminal_states
    }

    class Polling {
      +Integer interval_ms
    }

    class Workspace {
      +String root
    }

    class Worker {
      +List~String~ ssh_hosts
      +Integer max_concurrent_agents_per_host
    }

    class Agent {
      +Integer max_concurrent_agents
      +Integer max_turns
      +Integer max_retry_backoff_ms
      +Map max_concurrent_agents_by_state
    }

    class Codex {
      +String command
      +StringOrMap approval_policy
      +String thread_sandbox
      +Map turn_sandbox_policy
      +Integer turn_timeout_ms
      +Integer read_timeout_ms
      +Integer stall_timeout_ms
    }

    class Hooks {
      +String after_create
      +String before_run
      +String after_run
      +String before_remove
      +Integer timeout_ms
    }

    class Observability {
      +Boolean dashboard_enabled
      +Integer refresh_ms
      +Integer render_interval_ms
    }

    class Server {
      +Integer port
      +String host
    }

    ConfigSchema *-- Tracker
    ConfigSchema *-- Polling
    ConfigSchema *-- Workspace
    ConfigSchema *-- Worker
    ConfigSchema *-- Agent
    ConfigSchema *-- Codex
    ConfigSchema *-- Hooks
    ConfigSchema *-- Observability
    ConfigSchema *-- Server
```

### 5.1 Custom Types & Pre-Processing
Before passing raw data to `Ecto.Changeset`, three pre-processing steps run:
1. `normalize_keys/1`: Atom keys and nested string keys are converted recursively into string keys.
2. `drop_nil_values/1`: `nil` values present in the input map are stripped away so that Ecto schema field default values take effect.
3. `StringOrMap` Ecto Type: Implemented for `codex.approval_policy` to permit either string values (e.g. `"never"`, `"on-request"`) or nested approval decision maps (`%{"reject" => ...}`).

### 5.2 Dynamic Sandbox Policy Resolution
Codex sessions require a turn sandbox policy describing directory read/write boundaries:
- If `codex.turn_sandbox_policy` is explicitly configured in `WORKFLOW.md`, that policy map is used.
- Otherwise, `Schema.resolve_runtime_turn_sandbox_policy/3` automatically generates a workspace-write sandbox policy targeting the issue workspace root:
```elixir
%{
  "type" => "workspaceWrite",
  "writableRoots" => [canonical_workspace_root],
  "readOnlyAccess" => %{"type" => "fullAccess"},
  "networkAccess" => false,
  "excludeTmpdirEnvVar" => false,
  "excludeSlashTmp" => false
}
```
For local execution runs, workspace paths are canonicalized through `SymphonyElixir.PathSafety.canonicalize/1` to resolve symlinks and enforce safe directory roots.

---

## 6. Environment Variable Indirection & Secret Management

To prevent hardcoding sensitive credentials or local machine file paths inside `WORKFLOW.md`, Symphony supports dynamic **Environment Variable Indirection**.

### 6.1 Indirection Syntax & Pattern Matching
Any string value beginning with a `$` character and matching regex `~r/^[A-Za-z_][A-Za-z0-9_]*$/` is treated as an environment variable reference (e.g. `$LINEAR_API_KEY`, `$SYMPHONY_WORKSPACE_ROOT`).

```elixir
defp env_reference_name("$" <> env_name) do
  if String.match?(env_name, ~r/^[A-Za-z_][A-Za-z0-9_]*$/) do
    {:ok, env_name}
  else
    :error
  end
end
```

### 6.2 Resolution Rules & Fallback Hierarchy
During `Schema.finalize_settings/1`, environment references are processed through dedicated fallback pipelines:

1. **API Key (`tracker.api_key`)**:
   - If `tracker.api_key` is specified as `$VAR`, lookup system env `System.get_env(VAR)`.
   - If `tracker.api_key` is `nil` or empty, fall back to `System.get_env("LINEAR_API_KEY")`.
   - If resolved value is an empty string `""`, it is normalized to `nil`.
2. **Assignee (`tracker.assignee`)**:
   - If specified as `$VAR`, lookup system env.
   - If `nil`, fall back to `System.get_env("LINEAR_ASSIGNEE")`.
3. **Workspace Root (`workspace.root`)**:
   - If specified as `$VAR`, lookup system env.
   - If missing or empty string, defaults to `Path.join(System.tmp_dir!(), "symphony_workspaces")`.

---

## 7. Prompt Builder Integration (`SymphonyElixir.PromptBuilder`)

`SymphonyElixir.PromptBuilder` compiles the Liquid prompt template extracted from `WORKFLOW.md` into the final prompt string delivered to Codex.

### 7.1 Template Compilation Pipeline
```elixir
def build_prompt(issue, opts \\ []) do
  template =
    Workflow.current()
    |> prompt_template!()
    |> parse_template!()

  template
  |> Solid.render!(
    %{
      "attempt" => Keyword.get(opts, :attempt),
      "issue" => issue |> Map.from_struct() |> to_solid_map()
    },
    [strict_variables: true, strict_filters: true]
  )
  |> IO.iodata_to_binary()
end
```

### 7.2 Struct Serialization to Solid Context
To prevent template rendering crashes when encountering Elixir structs, `to_solid_value/1` recursively converts structures:
- `%DateTime{}`, `%NaiveDateTime{}`, `%Date{}`, `%Time{}` -> Converted via `to_iso8601/1`.
- Struct maps (`%Issue{}`) -> Unpacked via `Map.from_struct/1` and keys converted to strings (`"identifier"`, `"title"`, etc.).
- Lists and maps -> Transformed recursively.

### 7.3 Default Fallback Prompt
If `WORKFLOW.md` contains an empty prompt section, `Config.workflow_prompt/0` supplies a built-in default:
```liquid
You are working on a Linear issue.

Identifier: {{ issue.identifier }}
Title: {{ issue.title }}

Body:
{% if issue.description %}
{{ issue.description }}
{% else %}
No description provided.
{% endif %}
```

---

## 8. Verification & Operational Testing

To verify the workflow parsing, configuration validation, and prompt generation pipeline:

### 8.1 ExUnit Integration Tests
Run the project ExUnit test suite for workspace and configuration:
```bash
cd elixir && mix test test/symphony_elixir/workspace_and_config_test.exs
```

### 8.2 Mix Code Quality Checks
Verify code specification compliance:
```bash
cd elixir && mix specs.check
```
