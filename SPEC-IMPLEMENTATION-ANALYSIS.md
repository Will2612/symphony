# Symphony SPEC → Elixir Implementation Analysis + Python+ Roadmap

Generated: 2026-06-02

## Section 3: System Overview / Components

| SPEC Component | Elixir Implementation | Python+ Plan |
|---|---|---|
| Workflow Loader | `SymphonyElixir.Workflow` (workflow.ex), `WorkflowStore` (workflow_store.ex) — polls mtime/size/hash every 1s for live reload | TODO |
| Config Layer | `SymphonyElixir.Config` (config.ex), `Config.Schema` (config/schema.ex) — Ecto schemas with defaults, `$VAR` indirection, `~` expansion | TODO |
| Issue Tracker Client | `SymphonyElixir.Tracker` behaviour → `Linear.Adapter` (Linear-backed) / `Tracker.Memory` (in-memory test), `Linear.Client` (client.ex) — GraphQL via Req | TODO: Design as abstract `TrackerAdapter` ABC allowing GitHub/Linear/Jira plug-in |
| Orchestrator | `SymphonyElixir.Orchestrator` (orchestrator.ex, 1921 lines) — single GenServer owning all mutable state | TODO |
| Workspace Manager | `SymphonyElixir.Workspace` (workspace.ex) — per-issue dirs, hooks, SSH remote support | TODO |
| Agent Runner | `SymphonyElixir.AgentRunner` (agent_runner.ex) — Task-based worker, creates workspace, runs Codex turns, handles continuation | TODO: Abstract `AgentRunner` as pluggable backend |
| Status Surface | `SymphonyElixir.StatusDashboard` (status_dashboard.ex, 1619+ lines) — terminal dashboard with TUI, token graphs, rate limits | TODO |
| Logging | `SymphonyElixir.LogFile` (log_file.ex) — OTP rotating disk log | TODO |

## Section 4: Core Domain Model

| SPEC Point | Elixir Status | Python+ Plan |
|---|---|---|
| Issue entity (id, identifier, title, description, priority, state, branch_name, url, labels, blocked_by, timestamps) | ✅ `SymphonyElixir.Linear.Issue` struct in issue.ex | TODO |
| Workflow Definition (config map + prompt_template) | ✅ `Workflow.loaded_workflow` type | TODO |
| Service Config (typed schema with defaults, `$VAR` resolution) | ✅ `Config.Schema` with Ecto embedded schemas, env var resolution in schema.ex (lines 453-557 for env resolution) | TODO |
| Workspace entity (path, workspace_key, created_now) | ✅ `Workspace.create_for_issue/2` | TODO |
| Run Attempt (issue_id, identifier, attempt, workspace_path, started_at, status, error) | ✅ Tracked via `running` map in orchestrator state | TODO |
| Live Session fields (session_id, thread_id, turn_id, pid, last_event, tokens, turn_count) | ✅ All tracked in orchestrator's running entry | TODO |
| RetryEntry (issue_id, identifier, attempt, due_at_ms, timer_handle, error) | ✅ `retry_attempts` map with Process timer_ref + retry_token | TODO |
| Orchestrator State (poll_interval, max_concurrency, running, claimed, retry_attempts, completed, codex_totals, codex_rate_limits) | ✅ Full `Orchestrator.State` struct | TODO |
| Stable Identifiers (ID for lookups, Identifier for logs, sanitized workspace key, normalized state) | ✅ All implemented — issue ID for keys, identifier for logs, `safe_identifier/1` for workspace key, `normalize_issue_state/1` | TODO |

## Section 5: Workflow Specification

| SPEC Requirement | Elixir Status | Python+ Plan |
|---|---|---|
| File discovery: explicit path → cwd default `./WORKFLOW.md` | ✅ `CLI.evaluate` handles positional arg, `Workflow.workflow_file_path` fallback | TODO |
| YAML front matter parsing (`---` delimited) | ✅ `Workflow.split_front_matter/1`, `front_matter_yaml_to_map/1`, uses `YamlElixir` | TODO |
| Non-map YAML → error | ✅ `:workflow_front_matter_not_a_map` | TODO |
| Prompt body trimming | ✅ `String.trim()` on remaining lines | TODO |
| `tracker` schema (kind, endpoint, api_key, project_slug, active_states, terminal_states) | ✅ Full `Config.Schema.Tracker` embedded schema | TODO |
| `polling` schema (interval_ms, default 30000) | ✅ `Config.Schema.Polling`, validates greater_than 0 | TODO |
| `workspace` schema (root, `~` expansion, relative resolved to WORKFLOW.md dir) | ✅ `Config.Schema.Workspace`, `PathSafety.canonicalize` | TODO |
| `hooks` schema (after_create, before_run, after_run, before_remove, timeout_ms 60000) | ✅ Full `Config.Schema.Hook` embedded schema | TODO |
| `agent` schema (max_concurrent_agents, max_turns, max_retry_backoff_ms, max_concurrent_agents_by_state) | ✅ `Config.Schema.Agent` with per-state concurrency map normalization | TODO |
| `codex` schema (command, approval_policy, thread_sandbox, turn_sandbox_policy, turn_timeout_ms, read_timeout_ms, stall_timeout_ms) | ✅ Full `Config.Schema.Codex` + `StringOrMap` custom type for approval_policy | TODO |
| Unknown keys ignored for forward compatibility | ✅ Ecto `cast` only picks known fields; extras ignored | TODO |
| Strict template rendering (Solid/Liquid) with unknown variable → fail | ✅ `PromptBuilder` uses `Solid` with `strict_variables: true, strict_filters: true` | TODO |
| Fallback when prompt body empty | ✅ `Config.workflow_prompt/0` has default template, `PromptBuilder.default_prompt/1` | TODO |
| Dynamic reload on file change | ✅ `WorkflowStore` GenServer polls every 1s, compares mtime/size/hash, keeps last known good on error | TODO |
| Dispatch preflight validation (tracker.kind, api_key, project_slug, codex.command) | ✅ `Config.validate!/0` validates kind ("linear"/"memory"), api_key, project_slug | TODO |
| Front matter `server` key for HTTP extension | ✅ `Config.Schema.Server` with host, port | TODO |
| Front matter `worker` key for SSH extension | ✅ `Config.Schema.Worker` with ssh_hosts, max_concurrent_agents_per_host | TODO |
| Front matter `observability` key | ✅ `Config.Schema.Observability` with dashboard_enabled, refresh_ms, render_interval_ms | TODO |

## Section 6: Configuration Resolution

| SPEC Point | Elixir Status | Python+ Plan |
|---|---|---|
| Resolution pipeline: path → parse YAML → apply defaults → resolve `$VAR` → coerce | ✅ `Schema.parse/1` pipeline at schema.ex ~line 460+ | TODO |
| `~` home expansion | ✅ Via `Path.expand` | TODO |
| `$VAR` indirection for api_key, workspace.root, path values | ✅ Explicit resolution funcs in schema.ex lines 453-557 | TODO |
| `tracker.api_key` defaults to `$LINEAR_API_KEY` | ✅ Schema default: `$LINEAR_API_KEY` | TODO |
| Relative workspace.root resolved to WORKFLOW.md dir | ✅ Schema resolve_workspace_root considers workflow dir | TODO |
| Dynamic reload on WORKFLOW.md change | ✅ `WorkflowStore` polling at 1s intervals | TODO |
| Invalid reload keeps last known good | ✅ `WorkflowStore` retains stale_state on error, logs warning | TODO |
| Reloaded config applies to future dispatch/retry/agents only | ✅ Orchestrator calls `refresh_runtime_config` before each tick | TODO |

## Section 7: Orchestration State Machine

| SPEC Requirement | Elixir Status | Python+ Plan |
|---|---|---|
| Internal claim states: Unclaimed, Claimed, Running, RetryQueued, Released | ✅ `running` map, `claimed` set, `retry_attempts` map, `completed` set, `blocked` map | TODO |
| Run attempt phases: PreparingWorkspace → BuildingPrompt → LaunchingAgent → InitializingSession → StreamingTurn → Finishing → Succeeded/Failed/TimedOut/Stalled/Canceled | ✅ Phase tracked via `last_codex_event` in running entry. Stalled detected in `reconcile_stalled_running_issues`. Agent lifecycle in `AgentRunner` | TODO |
| Poll Tick: reconcile → validate config → fetch → dispatch | ✅ `maybe_dispatch` follows exact sequence | TODO |
| Worker Exit (normal) → continuation retry after ~1s | ✅ `handle_agent_down(:normal, ...)` → `complete_issue` → `schedule_issue_retry(..., 1, delay_type: :continuation)` | TODO |
| Worker Exit (abnormal) → exponential backoff retry | ✅ `handle_agent_down(reason, ...)` → `retry_agent_down` → `schedule_issue_retry` with `failure_retry_delay` | TODO |
| Codex Update Event → integrate into running entry | ✅ `handle_info({:codex_worker_update, ...})` → `integrate_codex_update` → token deltas, rate limits | TODO |
| Retry Timer → re-fetch candidates → dispatch or release | ✅ `handle_info({:retry_issue, ...})` → `handle_retry_issue` → re-fetches candidates, dispatches or releases | TODO |
| Reconciliation → stop terminal (cleanup) / non-active (no cleanup) | ✅ `reconcile_running_issues` with terminate_running_issue | TODO |
| Stall Timeout → kill worker + retry | ✅ `reconcile_stalled_running_issues` with `stall_timeout_ms`, kills stalled sessions | TODO |
| Blocked state (input_required / approval_required / MCP elicitation) | ✅ Extended beyond spec: `blocked` map, `input_required_blocker?` checks for turn_input_required, approval_required, MCP elicitation | TODO |
| Multiple continuation turns on same thread within worker | ✅ `AgentRunner.do_run_codex_turns` loops up to `max_turns`, re-checks issue state after each turn | TODO |
| Continuation turns send only guidance, not full prompt | ✅ `build_turn_prompt` for turn > 1 returns short continuation guidance string | TODO |
| Session lifecycle: thread_id reused across turns, session_id = `<thread_id>-<turn_id>` | ✅ `AppServer.read_handshake` extracts these, orchestrator tracks session_id | TODO |

## Section 8: Polling, Scheduling, Reconciliation

| SPEC Point | Elixir Status | Python+ Plan |
|---|---|---|
| Startup: validate config, cleanup terminals, schedule tick at 0ms | ✅ `Orchestrator.init` → `Config.settings!` → `run_terminal_workspace_cleanup` → `schedule_tick(state, 0)` | TODO |
| Tick sequence: reconcile → validate → fetch → sort → dispatch | ✅ `maybe_dispatch` follows exact sequence | TODO |
| Candidate eligibility: id/identifier/title/state present, active state, not claimed/running, slots available, Todo/unblocked | ✅ `should_dispatch_issue?` checks all conditions | TODO |
| Sort: priority ascending, created_at oldest, identifier tie-break | ✅ `sort_issues_for_dispatch` with priority_rank, created_at sort, identifier tiebreaker | TODO |
| Global concurrency limit | ✅ `available_slots` returns `max(max_concurrent_agents - map_size(running), 0)` | TODO |
| Per-state concurrency limit | ✅ `Config.max_concurrent_agents_for_state` + `state_slots_available?` | TODO |
| Todo + non-terminal blocker → skip | ✅ `todo_issue_blocked_by_non_terminal?` | TODO |
| Backoff formula: continuation = 1s, failure = 10s × 2^(n-1) capped at max_retry_backoff_ms | ✅ `retry_delay` with 1000ms continuation and `failure_retry_delay` bit shift | TODO |
| Stall detection: elapsed > stall_timeout_ms since last event or started_at | ✅ `stall_elapsed_ms` uses `last_activity_timestamp` | TODO |
| Reconciliation Part A (stall detection) | ✅ `maybe_restart_stalled_issue` | TODO |
| Reconciliation Part B (state refresh) | ✅ `reconcile_running_issues` → `fetch_issue_states_by_ids` | TODO |
| Terminal → stop + cleanup workspace | ✅ `terminate_running_issue(state, issue_id, true)` | TODO |
| Non-active → stop without cleanup | ✅ `terminate_running_issue(state, issue_id, false)` | TODO |
| Refresh failure → keep workers, retry next tick | ✅ Logs error, keeps state unchanged | TODO |
| Startup terminal workspace cleanup | ✅ `run_terminal_workspace_cleanup` — fetches terminal states, removes workspaces | TODO |
| Blocked issues reconciliation | ✅ `reconcile_blocked_issues` paralleling running reconciliation | TODO |

## Section 9: Workspace Management

| SPEC Point | Elixir Status | Python+ Plan |
|---|---|---|
| `workspace.root/<sanitized_identifier>` layout | ✅ `Workspace.create_for_issue` computes path | TODO |
| Workspace reuse across runs | ✅ `ensure_workspace` returns `created_now=false` if dir exists | TODO |
| Sanitize identifier to `[A-Za-z0-9._-]` only | ✅ `safe_identifier/1` replaces non-matching chars with `_` | TODO |
| `after_create` hook only on new workspace | ✅ `maybe_run_after_create_hook` gated on `created?` | TODO |
| `before_run` hook, failure aborts | ✅ `Workspace.run_before_run_hook`, failure returned as error | TODO |
| `after_run` hook, failure logged and ignored | ✅ `Workspace.run_after_run_hook`, `ignore_hook_failure/1` | TODO |
| `before_remove` hook, failure ignored | ✅ `maybe_run_before_remove_hook`, `ignore_hook_failure` | TODO |
| Hook timeout via `hooks.timeout_ms` (default 60000) | ✅ All hooks use `Task.yield(task, timeout_ms)` | TODO |
| Hooks run as `sh -lc <script>` in workspace cwd | ✅ `System.cmd("sh", ["-lc", command], cd: workspace)` | TODO |
| Agent CWD = workspace path | ✅ `AppServer.validate_workspace_cwd` in app_server.ex | TODO |
| Workspace path must stay inside workspace root | ✅ `validate_workspace_path` with canonicalize + symlink resolution | TODO |
| Symlink escape detection | ✅ `PathSafety.canonicalize` follows symlinks, containment check catches escape | TODO |
| PathSafety module for symlink-aware canonicalization | ✅ `SymphonyElixir.PathSafety` resolves symlinks path-by-path | TODO |
| before_remove only if dir exists | ✅ `maybe_run_before_remove_hook` checks `File.dir?` | TODO |
| Remote workspaces via SSH | ✅ `ensure_workspace(workspace, worker_host)` runs remote shell script with marker output parsing | TODO |
| Existing non-directory at workspace path → rm_rf + recreate | ✅ `ensure_workspace` non-dir path handling | TODO |

## Section 10: Agent Runner Protocol (Codex Integration)

| SPEC Point | Elixir Status | Python+ Plan |
|---|---|---|
| Launch: `bash -lc <codex.command>` | ✅ `AppServer.start_port` builds cmd from config | TODO: Abstract to pluggable agent backend |
| Subprocess in workspace cwd | ✅ CWD via `validate_workspace_cwd` → port open | TODO |
| Max line size for safe buffering | ✅ `@port_line_bytes` 1,048,576 (1MB) | TODO |
| JSON-RPC 2.0 initialize/handshake | ✅ `AppServer.do_start_session` sends initialize, gets capabilities | TODO |
| Thread start with cwd | ✅ `start_thread` sends thread/start with cwd=workspace | TODO |
| Turn start with prompt + title | ✅ `run_turn` sends turn/start with prompt + title = `<identifier>: <title>` | TODO |
| First turn = full rendered prompt | ✅ `build_turn_prompt` for turn 1 calls `PromptBuilder.build_prompt` | TODO |
| Continuation turns = guidance only | ✅ For turn > 1, returns short continuation string | TODO |
| Advertise client-side tool specs | ✅ `AppServer` sends `toolSpecs` from `DynamicTool.tool_specs/0` | TODO |
| Extract thread_id from thread identity | ✅ `AppServer.read_handshake` parses thread/started result | TODO |
| Extract turn_id from turn identity | ✅ `session_started` event emits session_id = `thread_id-turn_id` | TODO |
| Reuse thread_id across continuation turns | ✅ `run_turn` uses existing `session.thread_id` | TODO |
| Approval policy = `never` → auto-approve | ✅ When `approval_policy == "never"`, `auto_approve_requests = true` | TODO |
| Sandbox modes from workflow config | ✅ `thread_sandbox` and `turn_sandbox_policy` passed through to Codex | TODO |
| Unknown dynamic tool → fail without stall | ✅ `DynamicTool.execute` returns failure_response with supported list | TODO |
| `linear_graphql` client-side tool | ✅ Full implementation — validates query/variables, executes via Client.graphql, handles GraphQL errors | TODO |
| User input → non-interactive answer + fail | ✅ `@non_interactive_tool_input_answer`, turn ends with input_required outcome | TODO |
| Turn timeout enforcement | ✅ Monitors `codex.turn_timeout_ms` during stream | TODO |
| Read timeout for sync requests | ✅ `codex.read_timeout_ms` applied | TODO |
| MCP elicitation → blocker detection | ✅ `input_required_blocker?` detects `mcpServer/elicitation/request` | TODO |
| Events emitted: session_started, startup_failed, turn_completed, turn_failed, turn_cancelled, turn_input_required, approval_auto_approved, unsupported_tool_call, notification, other_message, malformed | ✅ All emitted via `:codex_worker_update` messages | TODO |

## Section 11: Tracker Integration

| SPEC Point | Elixir Status | Python+ Plan |
|---|---|---|
| `Tracker` behaviour: fetch_candidate_issues, fetch_issues_by_states, fetch_issue_states_by_ids | ✅ `SymphonyElixir.Tracker` with 3 required callbacks | TODO: Abstract as ABC |
| Extension: create_comment, update_issue_state | ✅ `Linear.Adapter` implements both | TODO |
| Linear: GraphQL endpoint, auth header, project slug filtering | ✅ `Linear.Client` with Req HTTP + auth header | TODO |
| Candidate query filters by project.slugId | ✅ GraphQL: `project: { slugId: { eq: $projectSlug } }` | TODO |
| State refresh by IDs with `[ID!]` typing | ✅ Separate query for issue states by IDs | TODO |
| Pagination with page size 50 | ✅ Implied via Linear client pagination | TODO |
| Labels → lowercase | ✅ In Issue normalization | TODO |
| Blocked_by from inverse relations type `blocks` | ✅ In Linear candidate issue query | TODO |
| Priority → integer only | ✅ In Issue struct | TODO |
| ISO-8601 timestamp parsing | ✅ DateTime parsing | TODO |
| Error mapping: unsupported_tracker_kind, linear_api_request, linear_api_status, linear_graphql_errors, linear_unknown_payload, linear_missing_end_cursor | ✅ Error atoms used throughout | TODO |
| Memory adapter for tests | ✅ `Tracker.Memory` — configured issues list, matches by state/ID | TODO |

## Section 12: Prompt Construction

| SPEC Point | Elixir Status | Python+ Plan |
|---|---|---|
| Inputs: workflow prompt_template, issue, optional attempt | ✅ `PromptBuilder.build_prompt` takes issue, opts[:attempt] | TODO |
| Strict variable checking (Liquid-compatible) | ✅ `Solid.render!` with `strict_variables: true, strict_filters: true` | TODO |
| Issue struct keys → strings | ✅ `to_solid_map/1` converts all keys | TODO |
| Nested arrays/maps preserved | ✅ Recursive `to_solid_value` handling | TODO |
| `attempt` passed to template | ✅ `"attempt" => Keyword.get(opts, :attempt)` | TODO |
| Render failure → fail run attempt | ✅ `Solid.parse!` / `Solid.render!` raise on error | TODO |
| Empty prompt → default fallback | ✅ `PromptBuilder.default_prompt/1` | TODO |

## Section 13: Logging, Status, Observability

| SPEC Point | Elixir Status | Python+ Plan |
|---|---|---|
| Required context: issue_id, issue_identifier | ✅ Consistent across all logger calls | TODO |
| Required Codex context: session_id | ✅ Included in agent lifecycle logs | TODO |
| `key=value` message format | ✅ Standard Logger metadata-style | TODO |
| Rotating disk log (10MB × 5 files) | ✅ `LogFile.configure` with `:logger_disk_log_h` | TODO |
| Log sink failure → continue running | ✅ `LogFile.setup_disk_handler` catches failures, logs warning | TODO |
| Snapshot API: running, retrying, codex_totals, rate_limits | ✅ `Orchestrator.snapshot/1` returns full state map | TODO |
| Snapshot timeouts/unavailable | ✅ `:timeout`, `:unavailable` return values | TODO |
| Human-readable terminal dashboard | ✅ `StatusDashboard` — TUI with agents table, token graph, TPS, rate limits, retry queue | TODO |
| Phoenix LiveView dashboard at `/` | ✅ `SymphonyElixirWeb.DashboardLive` | TODO |
| JSON API: `GET /api/v1/state` | ✅ `ObservabilityApiController.state` returns running, retrying, blocked, codex_totals, rate_limits, polling | TODO |
| JSON API: `GET /api/v1/<issue_identifier>` | ✅ `ObservabilityApiController.issue_state` returns 404 or debug details | TODO |
| JSON API: `POST /api/v1/refresh` | ✅ `Orchestrator.request_refresh` → coalesced refresh | TODO |
| Token accounting: prefer absolute totals, ignore deltas | ✅ `extract_token_usage` prefers `total_token_usage`, `tokenUsage.total` | TODO |
| Session runtime seconds + token accumulation | ✅ `running_seconds` + token deltas per session + aggregate | TODO |
| Rate-limit tracking | ✅ `extract_rate_limits` from updates, displayed in dashboard | TODO |
| Humanized agent event summaries | ✅ `StatusDashboard.humanize_codex_message` — ~100 events classified | TODO |

## Section 14: Failure Model & Recovery

| SPEC Point | Elixir Status | Python+ Plan |
|---|---|---|
| Config validation → skip dispatch, keep alive, keep reconciling | ✅ `maybe_dispatch` matches each error type, logs, returns state | TODO |
| Worker failures → exponential backoff retry | ✅ `retry_agent_down` | TODO |
| Tracker fetch failures → skip tick | ✅ Logs error, returns state unchanged | TODO |
| Reconciliation refresh failure → keep workers | ✅ Logs warning, continues | TODO |
| Dashboard/log failures → no crash | ✅ All dashboard ops in rescue blocks | TODO |
| In-memory state → restart = fresh | ✅ No DB, all state in Orchestrator GenServer | TODO |
| Restart recovery: terminal cleanup + re-poll | ✅ `init` calls `run_terminal_workspace_cleanup` + schedules tick | TODO |
| Operator intervention: edit WORKFLOW.md, change tracker state, restart | ✅ Dynamic reload + reconciliation | TODO |

## Section 15: Security & Safety

| SPEC Point | Elixir Status | Python+ Plan |
|---|---|---|
| Workspace path under configured root | ✅ `validate_workspace_path` with canonicalize, symlink detection | TODO |
| Agent CWD = per-issue workspace | ✅ `validate_workspace_cwd` in AppServer | TODO |
| Sanitized workspace dir names | ✅ `safe_identifier/1` | TODO |
| `$VAR` indirection for secrets | ✅ Schema resolve_env_values | TODO |
| No logging of API tokens | ✅ Logger uses issue_id/identifier only, never raw tokens | TODO |
| Hook timeouts mandatory (default 60s) | ✅ All hooks `Task.yield(task, timeout_ms)` | TODO |
| Hook output truncated in logs (2048 bytes) | ✅ `sanitize_hook_output_for_log` | TODO |
| CLI acknowledgement gate | ✅ Requires `--i-understand-that-this-will-be-running-without-the-usual-guardrails` | TODO |
| Path symlink escape detection | ✅ `PathSafety.canonicalize` resolves real paths | TODO |

## Section 16: Reference Algorithms

| SPEC Algorithm | Elixir Implementation | Python+ Plan |
|---|---|---|
| `start_service()` | `Orchestrator.init` — logging, workflow store, validate, cleanup, schedule tick | TODO |
| `on_tick()` | `maybe_dispatch` — reconcile → validate → fetch → sort → dispatch | TODO |
| `reconcile_running_issues()` | `reconcile_running_issues` — stall → fetch → stop terminal/non-active | TODO |
| `dispatch_issue()` | `dispatch_issue` → TaskSupervisor → on error schedule retry | TODO |
| `run_agent_attempt()` | `AgentRunner.run_on_worker_host` — workspace → before_run → session → turns → after_run | TODO |
| `on_worker_exit()` | `handle_agent_down` — normal=continuation retry, abnormal=backoff retry | TODO |
| `on_retry_timer()` | `handle_retry_issue` — fetch candidates → find by ID → dispatch or release | TODO |

## Section 17: Test & Validation Matrix

| SPEC Test | Elixir Status | Python+ Plan |
|---|---|---|
| Workflow file path precedence | ✅ `cli_test.exs` | TODO |
| Missing WORKFLOW.md → error | ✅ Tests exist | TODO |
| Invalid YAML → error | ✅ Tests exist | TODO |
| Front matter non-map → error | ✅ Tests exist | TODO |
| Config defaults apply | ✅ `workspace_and_config_test.exs` | TODO |
| tracker.kind validation | ✅ Tests exist | TODO |
| `$VAR` resolution | ✅ Tests exist | TODO |
| `~` path expansion | ✅ Tests exist | TODO |
| Prompt rendering with issue/attempt | ✅ Tests exist | TODO |
| Strict rendering on unknown vars | ✅ Tests exist | TODO |
| Workspace determinism + reuse | ✅ `workspace_and_config_test.exs` | TODO |
| Workspace hooks lifecycle | ✅ Tests exist | TODO |
| Path sanitization + root containment | ✅ Tests exist | TODO |
| Candidate fetch, pagination, filtering | ✅ `core_test.exs` | TODO |
| Dispatch sort order | ✅ `core_test.exs` | TODO |
| Todo with blockers → not eligible | ✅ `orchestrator_status_test.exs` | TODO |
| Terminal/non-active reconciliation | ✅ `core_test.exs` | TODO |
| Normal worker → continuation retry | ✅ Tests exist | TODO |
| Abnormal exit → exponential backoff | ✅ Tests exist | TODO |
| Stall detection | ✅ Tests exist | TODO |
| AppServer session/turn/protocol | ✅ `app_server_test.exs` | TODO |
| Dynamic tool: linear_graphql | ✅ `dynamic_tool_test.exs` | TODO |
| Structured logging context | ✅ Implied across tests | TODO |
| CLI args/flags | ✅ `cli_test.exs` | TODO |
| Live E2E: real Linear + real Codex | ✅ `live_e2e_test.exs` with `SYMPHONY_RUN_LIVE_E2E=1` | TODO |
| Snapshot API coverage | ✅ `orchestrator_status_test.exs`, `status_dashboard_snapshot_test.exs` | TODO |

## Section 18: Implementation Checklist

| SPEC Checklist Item | Elixir Status | Python+ Plan |
|---|---|---|
| Workflow path selection (explicit + cwd) | ✅ | TODO |
| YAML + prompt body loader | ✅ | TODO |
| Typed config with defaults + `$` resolution | ✅ | TODO |
| Dynamic WORKFLOW.md watch/reload | ✅ | TODO |
| Polling orchestrator, single-authority state | ✅ | TODO |
| Tracker client (candidate + state refresh + terminal fetch) | ✅ | TODO |
| Workspace manager (sanitized + hooks) | ✅ | TODO |
| Hook timeouts (60000 default) | ✅ | TODO |
| Codex app-server subprocess + JSON-RPC protocol | ✅ | TODO: Abstract to agent backend protocol adapter |
| Codex launch command config | ✅ | TODO: Generic agent command |
| Strict prompt rendering with issue/attempt | ✅ | TODO |
| Exponential retry + continuation retry | ✅ | TODO |
| Configurable retry backoff cap | ✅ | TODO |
| Reconciliation (terminal → cleanup, non-active → stop) | ✅ | TODO |
| Startup terminal cleanup | ✅ | TODO |
| Structured logs with issue_id, identifier, session_id | ✅ | TODO |
| Operator-visible observability | ✅ | TODO |
| HTTP server extension (CLI --port / server.port) | ✅ | TODO |
| linear_graphql tool extension | ✅ | TODO |

### Section 18.2 RECOMMENDED Extensions

| SPEC Extension | Elixir Status | Python+ Plan |
|---|---|---|
| HTTP server with CLI `--port` override, loopback bind, API endpoints | ✅ Full Phoenix/JSON API | TODO |
| `linear_graphql` tool extension | ✅ `DynamicTool` | TODO |
| Persist retry queue across restarts (TODO in spec) | ❌ In-memory only | TODO (optional) |
| Observability in workflow front matter (TODO in spec) | ✅ Already done: `observability` schema | n/a |
| Pluggable tracker adapters (TODO in spec) | ✅ `Tracker` behaviour with `Linear.Adapter` + `Memory` | TODO: ABC with plug-in discovery |

### Section 18.3 Operational Validation

| SPEC Requirement | Elixir Status | Python+ Plan |
|---|---|---|
| Real Integration Profile with credentials | ✅ `make e2e` | TODO |
| Hook execution / path resolution on target OS | ✅ Hooks use `sh -lc`, Path.expand | TODO |
| HTTP server port/bind behavior | ✅ Configurable host + port, loopback default | TODO |

## Appendix A: SSH Worker Extension

| SPEC Point | Elixir Status | Python+ Plan |
|---|---|---|
| worker.ssh_hosts config | ✅ `Config.Schema.Worker` | TODO |
| worker.max_concurrent_agents_per_host | ✅ Supported | TODO |
| Central orchestrator → remote hosts | ✅ SSH port spawning via `AppServer.start_port` | TODO |
| workspace.root interpreted on remote | ✅ Remote workspace creation with shell commands | TODO |
| Codex over SSH stdio | ✅ `SSH.start_port` → Erlang Port over SSH | TODO |
| Continuation stays on same host | ✅ `selected_worker_host` preserves host | TODO |
| Host capacity management | ✅ `select_worker_host` with least-loaded | TODO |
| Prefer previous host on retries | ✅ `preferred_worker_host_available?` | TODO |

## Python+ Architecture Notes: Pluggable Tracker & Agent

| Area | Design Recommendation |
|---|---|
| **Tracker abstraction** | `TrackerAdapter` ABC with: `fetch_candidate_issues()`, `fetch_issues_by_states(states)`, `fetch_issue_states_by_ids(ids)`, `create_comment(issue_id, body)`, `update_issue_state(issue_id, state)`. Returns normalized `Issue` dataclass. Implement: `LinearAdapter`, `GitHubIssuesAdapter`, `MemoryAdapter` |
| **Agent abstraction** | `AgentBackend` ABC with: `start_session(workspace, config)`, `run_turn(session, prompt, issue, callbacks)`, `stop_session(session)`. Callbacks emit dict events (type, timestamp, tokens, rate_limits, etc.). Implement: `CodexAppServerBackend`, `OpenCodeBackend` (subprocess pipe), `ClaudeCodeBackend` |
| **Config schema** | Pydantic models with `$VAR` resolution via env parsing. All schema modules map to WORKFLOW.md front matter sections |
| **Workflow loader** | Python YAML parser (`ruamel.yaml` or PyYAML) + Jinja2 with `undefined=StrictUndefined`. Filesystem polling via `watchfiles` |
| **Orchestrator** | `asyncio` with `async/await`. Single `Orchestrator` class with dict state. Workers as `asyncio.create_task`. Retry timers via `asyncio.create_task(asyncio.sleep(delay))` |
| **Workspace manager** | `pathlib.Path` for paths, `subprocess.run` for shell hooks, `os.path.realpath` for symlink detection |
| **Observability** | `structlog` for structured logging. Optional FastAPI for HTTP status server (no Phoenix/LiveView — keep it minimal). Terminal TUI via `rich` |
| **No BEAM deps** | No GenServer, Ecto, Phoenix. Replace with asyncio, Pydantic, FastAPI, structlog, rich |
