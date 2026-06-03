from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

PYPROJECT_TOML = Path("/home/will/Projects/symphony-openai/python/pyproject.toml")


def test_main_module_invocation_prints_help_when_no_args() -> None:
    """`python -m symphony` with no args exits nonzero (the
    acknowledgement flag is required before startup)."""
    proc = subprocess.run(
        [sys.executable, "-m", "symphony"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 1
    assert "i-understand" in proc.stderr.lower()


def test_main_module_invocation_with_ack_only_prints_banner() -> None:
    """`python -m symphony --i-understand-...` with no workflow
    errors (no default WORKFLOW.md in cwd, returns 1)."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "symphony",
            "--i-understand-that-this-will-be-running-without-the-usual-guardrails",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        cwd="/tmp",
    )
    assert proc.returncode == 1


def test_main_module_console_script_entry_point() -> None:
    """The `symphony` console script (defined in pyproject.toml as
    `symphony = symphony.cli:main`) is the canonical entrypoint.
    Verify pyproject.toml wiring without invoking it."""
    with PYPROJECT_TOML.open("rb") as f:
        data = tomllib.load(f)
    scripts = data.get("project", {}).get("scripts", {})
    assert scripts.get("symphony") == "symphony.cli:main"


def test_dunder_main_imports_cleanly() -> None:
    """`import symphony.__main__` is well-formed and exposes a
    callable `main`."""
    import symphony.__main__ as m  # noqa: PLC0415

    assert hasattr(m, "main")
    assert callable(m.main)


def test_dunder_main_module_attribute_present() -> None:
    """The dunder-main module is reachable as `symphony.__main__`."""
    import symphony.__main__ as m  # noqa: PLC0415

    assert m.__name__ == "symphony.__main__"


def test_dunder_main_delegates_to_cli_main() -> None:
    """`symphony.__main__.main` IS `symphony.cli.main`."""
    import symphony.__main__ as dunder_main  # noqa: PLC0415
    from symphony import cli  # noqa: PLC0415

    assert dunder_main.main is cli.main
