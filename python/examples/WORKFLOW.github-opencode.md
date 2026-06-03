---
# Symphony WORKFLOW.md example — GitHub Issues + OpenCode runner
#
# This is the recommended starting point for a project that wants
# to drive Symphony against GitHub Issues with the OpenCode coding
# agent (via the Agent Client Protocol over stdio).
#
# SPEC §5.3 enumerates the full set of top-level keys. Anything not
# listed here falls back to the Pydantic defaults in
# `symphony.config.schema.SymphonyConfig`.
#
# Required env vars:
#   $GITHUB_TOKEN  — a personal access token with `repo` scope
#                    (also the default token name; `api_key` may
#                    reference a different secret).
#
# Run with:
#   symphony --i-understand-that-this-will-be-running-without-the-usual-guardrails \
#            --logs-root ./logs --port 7842 \
#            examples/WORKFLOW.github-opencode.md

tracker:
  # GitHub Issues adapter. `kind: github` is the v1 default.
  kind: github
  # The `GITHUB_TOKEN` env var is expanded at config-load time
  # (gated to fields whose semantics are a credential).
  api_key: $GITHUB_TOKEN
  # The repo's owner/name, e.g. "openai/symphony".
  project_slug: "openai/symphony"
  # Issues in these states are eligible for dispatch.
  active_states:
    - open
  # Issues in these states are considered terminal (no further
  # dispatch; SPEC §8.6 terminal cleanup runs at boot).
  terminal_states:
    - closed
  # Custom endpoint for GitHub Enterprise; defaults to public.
  # endpoint: "https://github.example.com/api/v3"

polling:
  # Orchestrator tick interval, in milliseconds. 30s is the SPEC
  # default; lower for fast-moving boards.
  interval_ms: 30000

workspace:
  # Where per-issue workspaces live. Each issue gets a subdirectory
  # named after its identifier. `~` and `$VAR` are expanded.
  root: ~/.cache/symphony/workspaces

hooks:
  # Per-issue hooks. The hook's stdout/stderr is captured and
  # truncated to 8 KB in the structured log.
  after_create: |
    # Clone the repo into the workspace. The hook is run from the
    # workspace cwd; `$1` is the issue identifier.
    git clone --depth 1 https://github.com/openai/symphony.git .
  before_run: |
    # Optional: pull latest before the agent starts.
    git fetch --all --prune
  after_run: |
    # Optional: clean up transient state.
    git status
  before_remove: |
    # Optional: archive the workspace before deletion.
    tar -czf /tmp/$1-workspace.tgz . || true
  # Hook timeout; default 60s.
  timeout_ms: 60000

agent:
  # Number of concurrent worker runs. Total = this * 1 worker per host.
  max_concurrent_agents: 5
  # Per-attempt turn cap (runner-specific). 50 is the SPEC default.
  max_turns: 50
  # Cap for exponential-backoff retries. 10m is the SPEC default.
  max_retry_backoff_ms: 600000

codex:
  # The runner command. Default is `opencode acp` (long-lived
  # stdio JSON-RPC session, matches SPEC §10.2 continuation
  # semantics).
  command: opencode acp
  # Auto-approve per SPEC §10.5: command and file-change prompts
  # are auto-approved for the session.
  approval_policy: auto-approve
  # Sandbox mode for the thread: workspace-write (the agent can
  # read anywhere, but only write inside the workspace).
  thread_sandbox: workspace-write
  # Per-turn sandbox policy. The agent's writable root is the
  # per-issue workspace path.
  turn_sandbox_policy:
    writable_roots:
      - ~/.cache/symphony/workspaces
  # Read timeout (inactivity on the stdio JSON-RPC pipe).
  read_timeout_ms: 30000
  # Turn timeout (wall time for one prompt → turn-final event).
  turn_timeout_ms: 3600000
  # Stall timeout (no event forwarded for N ms while in a turn).
  # 0 disables stall detection entirely (SPEC §8.5).
  stall_timeout_ms: 300000

server:
  # Bind host for the observability HTTP server. 127.0.0.1 = local
  # only; bind to 0.0.0.0 only on trusted networks.
  host: 127.0.0.1
  # Bind port. 0 = ephemeral; the actual port is written to
  # `<logs_root>/port` and logged.
  port: 7842
  # Optional: file path for the structured log tee. Empty = stderr
  # only. The directory is auto-created.
  log_file: ""

logs_root: ./logs

worker:
  # Optional. Parsed but unused in v1 (Appendix A SSH worker
  # extension deferred to v2).
  ssh_hosts: []
  max_concurrent_agents_per_host: 1
---

You are working on a GitHub Issue `{{ issue.identifier }}`.

{% if attempt %}
This is retry attempt #{{ attempt }} because the issue is still in
an active state. Resume from the current workspace state instead of
restarting from scratch. Do not repeat already-completed
investigation or validation unless it is needed for new code changes.
{% endif %}

Issue context:
- Identifier: `{{ issue.identifier }}`
- Title: `{{ issue.title }}`
- State: `{{ issue.state }}`
- Labels: `{{ issue.labels }}`
- URL: `{{ issue.url }}`
- Blocked by: `{{ issue.blocked_by | default('[]') }}`

Description:
{% if issue.description %}
{{ issue.description }}
{% else %}
_(no description provided)_
{% endif %}

Instructions:
1. Inspect the workspace (already cloned by the `after_create` hook).
2. Use `git log --oneline -20`, `git status`, and `git diff` to
   understand the current state.
3. If the issue requires code changes, implement them in a feature
   branch and commit them.
4. Open a pull request titled `[{{ issue.identifier }}] {{ issue.title }}`
   and link it in the issue's comments.
5. Reply to the issue with a summary of the work done.
