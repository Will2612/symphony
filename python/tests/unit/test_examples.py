from __future__ import annotations

import os
import tomllib
from pathlib import Path

from symphony.config.schema import SymphonyConfig
from symphony.config.validate import preflight
from symphony.workflow.loader import load

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


def test_examples_dir_exists() -> None:
    assert EXAMPLES_DIR.is_dir()
    assert any(EXAMPLES_DIR.glob("WORKFLOW.*.md"))


def test_github_opencode_workflow_loads() -> None:
    """The GitHub + OpenCode example parses into a valid
    `SymphonyConfig` with the expected kind."""
    workflow = load(EXAMPLES_DIR / "WORKFLOW.github-opencode.md")
    assert workflow.front_matter["tracker"]["kind"] == "github"
    assert workflow.front_matter["codex"]["command"] == "opencode acp"
    assert "opencode" in str(workflow.body) or "GitHub Issue" in str(workflow.body)


def test_memory_dev_workflow_loads() -> None:
    """The memory-dev example parses into a valid `SymphonyConfig`
    with `kind: memory`."""
    workflow = load(EXAMPLES_DIR / "WORKFLOW.memory-dev.md")
    assert workflow.front_matter["tracker"]["kind"] == "memory"
    assert workflow.front_matter["server"]["port"] == 0


def test_github_opencode_workflow_validates() -> None:
    """The GitHub example passes the config preflight when the
    required env vars are set."""
    os.environ.setdefault("GITHUB_TOKEN", "dummy-token-for-preflight")
    workflow = load(EXAMPLES_DIR / "WORKFLOW.github-opencode.md")
    config = SymphonyConfig.model_validate(workflow.front_matter)
    preflight(config)  # raises on failure


def test_memory_dev_workflow_validates() -> None:
    """The memory-dev example passes the config preflight without
    any env vars."""
    workflow = load(EXAMPLES_DIR / "WORKFLOW.memory-dev.md")
    config = SymphonyConfig.model_validate(workflow.front_matter)
    preflight(config)  # raises on failure


def test_github_opencode_workflow_has_prompt_body() -> None:
    """The example's prompt body uses the required Jinja2
    variables (`issue.identifier`, `issue.title`, `attempt`)."""
    workflow = load(EXAMPLES_DIR / "WORKFLOW.github-opencode.md")
    assert "issue.identifier" in workflow.body
    assert "issue.title" in workflow.body
    assert "attempt" in workflow.body


def test_memory_dev_workflow_has_prompt_body() -> None:
    """The memory-dev example's prompt body uses `issue.identifier`."""
    workflow = load(EXAMPLES_DIR / "WORKFLOW.memory-dev.md")
    assert "issue.identifier" in workflow.body


def test_github_opencode_workflow_uses_expansion() -> None:
    """`$GITHUB_TOKEN` and `~/.cache/...` are referenced; the
    resolution module handles them at config-load time."""
    workflow = load(EXAMPLES_DIR / "WORKFLOW.github-opencode.md")
    assert "$GITHUB_TOKEN" in workflow.front_matter["tracker"]["api_key"]
    assert "~/.cache" in workflow.front_matter["workspace"]["root"]


def test_examples_are_listed_in_distribution() -> None:
    """The examples live in the repo under `python/examples/` and
    are not part of the importable `symphony` package; consumers
    copy the file from the repo."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    with pyproject.open("rb") as f:
        data = tomllib.load(f)
    assert (Path(__file__).resolve().parents[2] / "examples").is_dir()
    # pyproject.toml does NOT need to list `examples/` in
    # package-data; consumers copy the file from the repo.
    assert data.get("project", {}).get("name") == "symphony-py"
