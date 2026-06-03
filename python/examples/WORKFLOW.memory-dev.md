---
# Symphony WORKFLOW.md example — in-memory tracker for dev / smoke tests
#
# `tracker.kind: memory` is the simplest adapter: an in-process
# issue store with no HTTP / no credentials. Use it to smoke-test
# the orchestrator, runner, and observability stack without
# configuring a real tracker.
#
# This file is referenced from `tests/unit/test_config_validate.py`
# and the `tracker_github.feature` BDD scenario
# "tracker.kind memory is accepted".
#
# Run with:
#   symphony --i-understand-that-this-will-be-running-without-the-usual-guardrails \
#            --logs-root ./logs --port 0 \
#            examples/WORKFLOW.memory-dev.md

tracker:
  # The in-process adapter. No HTTP requests; no `api_key`.
  # Suitable for development, smoke tests, and conformance
  # suites.
  kind: memory
  # `active_states` / `terminal_states` are honored for filtering
  # exactly the same way as the GitHub adapter.
  active_states:
    - open
  terminal_states:
    - closed

polling:
  # Aggressive polling for fast feedback in dev. Production
  # deployments should keep the 30s default.
  interval_ms: 5000

workspace:
  # Use a tmp-style path under `logs_root` so dev workspaces are
  # easy to clean up between runs.
  root: ./logs/workspaces

hooks:
  # In dev we skip the git clone; the workspace is created empty
  # and the agent starts from a blank slate.
  after_create: |
    echo "Workspace created for $1"
  before_remove: |
    echo "Workspace removed for $1"

agent:
  # Single concurrent agent so the dev log is easy to read.
  max_concurrent_agents: 1
  max_turns: 10
  max_retry_backoff_ms: 30000

codex:
  # Default runner: `opencode acp` over stdio.
  command: opencode acp
  approval_policy: auto-approve
  thread_sandbox: workspace-write
  turn_sandbox_policy:
    writable_roots:
      - ./logs/workspaces
  read_timeout_ms: 30000
  turn_timeout_ms: 600000
  stall_timeout_ms: 0  # disabled in dev; we want to see hangs

server:
  host: 127.0.0.1
  # Ephemeral port — the actual port is logged and written to
  # `<logs_root>/port`. This is the SPEC §13.7 default.
  port: 0
  log_file: ""

logs_root: ./logs

worker:
  ssh_hosts: []
  max_concurrent_agents_per_host: 1
---

You are working on an in-memory issue `{{ issue.identifier }}`.

This is a dev / smoke-test workflow; the orchestrator will dispatch
the issue to the runner, the runner will attempt to do useful work
inside the workspace, and you'll see the results in the structured
log + observability HTTP server.

Issue context:
- Identifier: `{{ issue.identifier }}`
- Title: `{{ issue.title }}`
- State: `{{ issue.state }}`
- Labels: `{{ issue.labels }}`
- URL: `{{ issue.url }}`

Description:
{% if issue.description %}
{{ issue.description }}
{% else %}
_(no description provided)_
{% endif %}
