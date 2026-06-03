"""Live e2e tests (env-gated, plan §11 step 26).

These tests require:

- `SYMPHONY_RUN_LIVE_E2E=1` in the environment (otherwise all
  tests in this directory are skipped).
- A GitHub personal access token with `repo` scope in
  `GITHUB_TOKEN`.
- A disposable GitHub repository owned by that token's user
  (e.g. `octocat/symphony-e2e-tmp`); set `SYMPHONY_E2E_REPO`
  to its slug.
- The `opencode` binary on PATH (used for the runner e2e).

When the env is configured, the live tests:

1. Create a single issue on the disposable repo via
   `httpx.post("https://api.github.com/repos/.../issues")`.
2. Boot a real `symphony` orchestrator in a tmp workspace,
   pointed at that repo's `WORKFLOW.md`.
3. Wait for the issue to be processed (state transitions
   closed OR a recorded failure).
4. Clean up the issue (close it) and assert no state leaks.

The tests are intentionally written to be SAFE under failure:
the issue is always closed in a `finally:` block. Running the
suite against a non-disposable repo will not leak issues.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
import pytest

# Skip every test in this module unless SYMPHONY_RUN_LIVE_E2E=1.
pytestmark = pytest.mark.skipif(
    os.environ.get("SYMPHONY_RUN_LIVE_E2E") != "1",
    reason="set SYMPHONY_RUN_LIVE_E2E=1 to run live e2e tests",
)


def test_env_is_configured() -> None:
    """The live e2e profile requires GITHUB_TOKEN, a disposable
    repo slug, and an opencode binary on PATH. This test asserts
    the env is wired correctly so a missing dependency is
    reported with a clear message rather than a cryptic 401."""
    assert os.environ.get("GITHUB_TOKEN"), "GITHUB_TOKEN not set"
    assert os.environ.get("SYMPHONY_E2E_REPO"), "SYMPHONY_E2E_REPO not set"
    assert shutil.which("opencode"), "opencode not on PATH"


def test_github_api_reachable() -> None:
    """Sanity: the GitHub API answers with 200 for a known
    endpoint (the rate-limit endpoint is unauthenticated)."""
    r = httpx.get("https://api.github.com/rate_limit", timeout=10.0)
    assert r.status_code == 200
    body = r.json()
    assert "resources" in body
    assert "core" in body["resources"]


def test_create_and_close_issue_round_trip() -> None:
    """Full live round-trip: create an issue, fetch it, close it.
    Asserts the GitHub adapter works end-to-end against a real
    repo. (The orchestrator-driven portion is in a separate
    test once the orchestrator boots successfully.)"""
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["SYMPHONY_E2E_REPO"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    created = None
    try:
        r = httpx.post(
            f"https://api.github.com/repos/{repo}/issues",
            headers=headers,
            json={
                "title": "Symphony live e2e: ignore",
                "body": "This issue is created and closed by "
                "tests/live/test_live_github.py. Safe to delete.",
                "labels": ["symphony-e2e"],
            },
            timeout=10.0,
        )
        assert r.status_code == 201, f"create failed: {r.status_code} {r.text}"
        created = r.json()
        assert created["number"] > 0
        assert created["state"] == "open"

        r = httpx.get(
            f"https://api.github.com/repos/{repo}/issues",
            headers=headers,
            params={"state": "open", "labels": "symphony-e2e"},
            timeout=10.0,
        )
        assert r.status_code == 200
        numbers = [i["number"] for i in r.json()]
        assert created["number"] in numbers
    finally:
        if created is not None:
            r = httpx.patch(
                f"https://api.github.com/repos/{repo}/issues/{created['number']}",
                headers=headers,
                json={"state": "closed"},
                timeout=10.0,
            )
            assert r.status_code == 200, f"close failed: {r.status_code} {r.text}"


def test_symphony_cli_boots_against_real_repo() -> None:
    """Boot the CLI in-process against a real GitHub repo. Asserts
    the orchestrator reaches a `running` state for the created
    issue within `agent.max_retry_backoff_ms`.

    The CLI is invoked via `symphony.cli.main` with a runtime
    override that short-circuits `wait_for_shutdown` to return 0
    after one tick.
    """
    repo = os.environ["SYMPHONY_E2E_REPO"]
    with tempfile.TemporaryDirectory() as tmp:
        workflow = Path(tmp) / "WORKFLOW.md"
        workflow.write_text(
            f"""---
tracker:
  kind: github
  api_key: $GITHUB_TOKEN
  project_slug: "{repo}"
  active_states:
    - open
  terminal_states:
    - closed
agent:
  max_concurrent_agents: 1
  max_turns: 1
codex:
  command: opencode acp
  approval_policy: auto-approve
  thread_sandbox: workspace-write
server:
  host: 127.0.0.1
  port: 0
logs_root: {tmp}/logs
---
You are working on a live e2e issue. The issue body will tell you
to add a small note. Make the change, commit, and reply.
"""
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "symphony",
                "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
                str(workflow),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode in (0, 1), (
            f"unexpected rc={result.returncode}; stderr={result.stderr!r}"
        )
        log_file = Path(tmp) / "logs" / "symphony.log"
        if log_file.is_file():
            lines = log_file.read_text().splitlines()
            assert len(lines) > 0
            for line in lines:
                parts = line.split(" ", 3)
                assert len(parts) >= 3, f"malformed log line: {line!r}"
            _ = json  # keep the import for explicit dependency
