---
# verify.workflow.md — Smoke-test stub for the deploy pipeline
#
# This WORKFLOW.md intentionally points at a non-existent GitHub repo
# with fake credentials.  When the orchestrator boots and tries to
# poll the tracker it will get a 401 or 404, proving the full boot
# path works (loader → config → tracker init → network call).
#
# The smoke test (verify.sh) checks the boot log for the expected
# error.  The orchestrator is NOT expected to dispatch any work.

tracker:
  # GitHub Issues adapter – the default for both implementations.
  kind: github
  # Deliberately fake token; GitHub will return 401.
  api_key: sk-fake-do-not-use
  # This repository does not exist on GitHub; the API call will
  # return 404 (or 404-via-403 for some endpoints).
  project_slug: "symphony-verify/does-not-exist"
  active_states:
    - open
  terminal_states:
    - closed

polling:
  # Fail fast — 2 seconds between ticks so the test doesn't wait.
  interval_ms: 2000

orchestrator:
  # Informational: record the intended provider and runner so
  # verify.sh can confirm the right runtime was selected.
  provider: opencode
  runner: opencode

agent:
  # Zero concurrent agents — this is a smoke test only.
  max_concurrent_agents: 0
  max_turns: 1
  max_retry_backoff_ms: 10000

workspace:
  root: /tmp/symphony-verify-workspaces

codex:
  command: echo "smoke-test-noop"
  approval_policy: auto-approve
  thread_sandbox: read-only
  read_timeout_ms: 1000
  turn_timeout_ms: 5000
  stall_timeout_ms: 0

logs_root: /tmp/symphony-verify-logs
---

Smoke-test workflow for the deploy pipeline.

This workflow is never expected to dispatch an agent run.  Instead it
validates that the orchestrator can:
1. Parse a `WORKFLOW.md` front matter.
2. Initialise the GitHub tracker client.
3. Make a live HTTPS call to the GitHub API.
4. Surface authentication / authorisation errors in the structured
   log as a fatal startup failure.

If you see a 401 (`Bad credentials`) or 404 (`Not Found`) in the boot
log the smoke test passes.
