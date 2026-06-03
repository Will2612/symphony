# Logging Best Practices

This guide defines logging conventions for Symphony so OpenCode / Codex / the
operator can diagnose failures quickly. It mirrors `elixir/docs/logging.md`
and is tailored to the Python implementation (per SPEC §13.1).

## Goals

- Make logs searchable by issue and session.
- Capture enough execution context to identify root cause without reruns.
- Keep messages stable so dashboards and alerts are reliable.
- Never leak secrets.

## Log Format

Each line is a single `key=value` flat record:

```
<ISO-8601 ms> <LEVEL> <logger> <message> [k=v k=v ...]
```

Concrete example:

```
2026-06-03T10:42:13.041Z INFO symphony.orchestrator tick_dispatched issue_id=ENG-1234 issue_identifier=ENG-1234 attempt=1 phase=PREPARING_WORKSPACE
```

The format is implemented by `symphony.observability.log.KvFormatter`.

## Required Context Fields

The `KvFormatter` carries a whitelisted set of structured fields. The
following fields are recognized and emitted as `k=v` pairs:

| Field | Type | When |
|---|---|---|
| `issue_id` | str | Always, when an issue is in scope. Stable foreign key. |
| `issue_identifier` | str | Always, when an issue is in scope. Human key (e.g. `ENG-1234`). |
| `session_id` | str | Always, when a runner session is in scope. |
| `attempt` | int | Per-attempt counter; increments on each retry. |
| `phase` | str | One of the `RunPhase` enum values (see `symphony.orchestrator.state`). |
| `error_code` | str | Stable error code (matches SPEC §10.6 / §11.4 / §14 categories). |

A logger call without these fields is still valid — the formatter just
omits the missing ones. A logger call with **extra** non-whitelisted
keys is dropped silently to keep the format stable.

## Forbidden Fields

The following field names (case-insensitive) are NEVER logged:

- `api_key`
- `password`
- `secret`
- `token`

`add_kv(record, key, value)` checks `is_forbidden(key)` and silently
drops the value. This is enforced at the log layer, not the call site.

## Message Design

- Use explicit `key=value` pairs in message text for high-signal fields.
- Prefer deterministic wording for recurring lifecycle events
  (e.g. `tick_dispatched`, `worker_started`, `turn_completed`).
- Include the action outcome (`completed`, `failed`, `retrying`) and the
  reason/error when available.
- Avoid logging large payloads unless required for debugging.
- Hook output is truncated to 8 KB in the structured log (per
  `symphony.workspace.hooks`).

## Scope Guidance

- `symphony.orchestrator.service`: log dispatch, retry, terminal /
  non-active transitions, worker exits with issue context. Include
  `session_id` whenever running-entry data has it.
- `symphony.runner.opencode`: log session start, completion, error
  with issue context and `session_id`.
- `symphony.workspace.manager`: log hook invocations (after_create,
  before_run, after_run, before_remove), workspace creation /
  removal, and `before_remove` archive paths.
- `symphony.tracker.github`: log fetch results, pagination boundaries,
  and rate-limit updates (with `reset_at`).

## Sink Failure Handling

`Symphony` writes to two sinks: stderr (always) and a tee'd file at
`<logs_root>/symphony.log` (if `server.log_file` is set). Each sink
runs through a `_SafeFileHandler` (or its console equivalent) that
swallows emit errors and writes a single `WARNING` line to stderr
instead of the default traceback. This guarantees that:

- A disk-full or permission-denied on the log file does not crash
  the orchestrator.
- An `OSError` on the stderr write does not bring down the
  observability layer.

## Configuration

`server.log_file = ""` (default) → stderr only.
`server.log_file = "<path>"` → stderr + the given file (directory
auto-created on first write).

The `logs_root` config field drives the default log file location
(`<logs_root>/symphony.log`) when the CLI is invoked with
`--logs-root <path>`.

## Checklist For New Logs

- Is this event tied to a tracker issue? Include `issue_id` and
  `issue_identifier`.
- Is this event tied to a runner session? Include `session_id`.
- Is the failure reason present and concise?
- Is the message format consistent with existing lifecycle logs?
- Are you using a non-forbidden key?
- Are you passing values that are str / int / float / bool / None
  (other values are `repr()`-formatted)?
