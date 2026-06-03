"""Helpers for BDD feature-file conformance checks.

Each feature file under `tests/features/` describes one SPEC §17
capability. Each scenario carries one or more `@unit-test("file.py::name")`
tags pointing to the unit tests asserting the scenario's behavior.
The BDD step file (`tests/steps/test_bdd_steps.py`) walks every
feature file and asserts every `@unit-test` tag resolves to a real
test in the suite.

Why this matters:
- BDD scenarios are a SPEC §17 → unit-test pointer map (a
  documentation contract), not a behavior contract.
- A scenario whose pointer is missing or broken is a conformance
  gap and must fail the build.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

_TAG_RE = re.compile(r'@unit-test\(["\']([^"\']+)["\']\)')


def _parse_gherkin_scenarios(feature_text: str) -> list[str]:
    """Return the list of scenario names in `feature_text`. Uses a
    tiny Gherkin subset parser — enough to identify `Scenario:`
    and `Background:` lines."""
    out: list[str] = []
    for line in feature_text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("Scenario:", "Scenario Outline:")):
            prefix = (  # type: ignore[assignment]
                "Scenario:" if stripped.startswith("Scenario:") else "Scenario Outline:"
            )
            name = stripped[len(prefix) :].strip()
            if "#" in name:
                name = name.split("#", 1)[0].strip()
            if name:
                out.append(name)
    return out


def _extract_pointer(scenario_docstring: str) -> str | None:
    """Legacy helper: extract a pointer from a docstring. Not used
    in the current tag-based scheme but kept for tests of the
    resolver itself."""
    m = re.search(r"# See (?:unit )?test ([^\n]+)$", scenario_docstring, re.MULTILINE)
    return m.group(1) if m else None


def _extract_tag_pointers(feature_text: str, scenario_name: str) -> list[str]:
    """Find all `@unit-test("file.py::name")` tags that belong to
    `scenario_name` in `feature_text` (the raw contents of the
    .feature file).

    The algorithm:
    1. Walk the file. Maintain a `pending` list of tags seen on
       the most recent lines.
    2. When you hit a blank line, discard `pending` (they
       belonged to the previous scenario, if any).
    3. When you hit `Scenario: <name>`, if `name` matches
       `scenario_name`, return the current `pending`.
    4. On any other line, append its `@unit-test` tags to
       `pending`.
    """
    pending: list[str] = []
    for line in feature_text.splitlines():
        stripped = line.strip()
        if not stripped:
            pending = []
            continue
        if stripped.startswith(("Scenario:", "Scenario Outline:")):  # type: ignore[arg-type]
            prefix = (  # type: ignore[assignment]
                "Scenario:" if stripped.startswith("Scenario:") else "Scenario Outline:"
            )
            name = stripped[len(prefix) :].strip()
            if "#" in name:
                name = name.split("#", 1)[0].strip()
            if name == scenario_name:
                return list(pending)
            pending = []
            continue
        for m in _TAG_RE.finditer(line):
            pending.append(m.group(1))
    return []


def _resolve_test_path(test_file: str) -> Path:
    """Resolve `tests/unit/test_xyz.py` to a real path."""
    if not test_file.startswith("tests/"):
        test_file = f"tests/unit/{test_file}"
    return Path(test_file)


def _resolve_test_function(test_path: Path, test_name: str) -> object:
    """Import the test module and look up `test_name`."""
    parts = list(test_path.with_suffix("").parts)
    if parts[0] != "tests":
        msg = f"unexpected test path: {test_path}"
        raise AssertionError(msg)
    parts[0] = "tests"
    module_name = ".".join(parts)
    module = importlib.import_module(module_name)
    fn = getattr(module, test_name, None)
    if fn is None:
        msg = f"test {test_name!r} not found in {module_name}"
        raise AssertionError(msg)
    return fn


def assert_pointer_resolves(pointer: str) -> None:
    """Given `test_xyz.py::test_yyy[+optional_params]` or just
    `test_xyz.py`, assert the test file exists.

    - A bare `test_xyz.py` (no `::`) asserts the file exists in
      `tests/unit/`.
    - A `test_xyz.py::test_yyy[+params]` form asserts the test
      function is importable.

    The function itself is invoked by the suite runner separately;
    here we only verify resolvability so a docstring typo is
    caught at BDD collection time.
    """
    raw = pointer.strip()
    # Strip optional parametrize suffix: foo[bar] -> foo
    if "[" in raw:
        raw = raw.split("[", 1)[0]
    if "::" in raw:
        test_file, test_name = raw.split("::", 1)
        test_path = _resolve_test_path(test_file)
        if not test_path.is_file():
            msg = f"test file {test_path} does not exist"
            raise AssertionError(msg)
        _resolve_test_function(test_path, test_name)
    else:
        # Bare file pointer.
        test_path = _resolve_test_path(raw)
        if not test_path.is_file():
            msg = f"test file {test_path} does not exist"
            raise AssertionError(msg)


def test_parse_gherkin_scenarios_extracts_names() -> None:
    text = """Feature: foo
  Scenario: bar
    Given x

  Scenario Outline: baz
    Given y

  Background:
    Given z
"""
    assert _parse_gherkin_scenarios(text) == ["bar", "baz"]


def test_extract_tag_pointers_finds_tags() -> None:
    text = """Feature: foo
  @unit-test("a.py::test_x")
  @unit-test("b.py::test_y")
  Scenario: bar
    Given x
"""
    pointers = _extract_tag_pointers(text, "bar")
    assert pointers == ["a.py::test_x", "b.py::test_y"]


def test_extract_tag_pointers_handles_missing_scenario() -> None:
    text = """Feature: foo
  @unit-test("a.py::test_x")
  Scenario: bar
"""
    pointers = _extract_tag_pointers(text, "qux")
    assert pointers == []


def test_extract_tag_pointers_stops_at_next_scenario() -> None:
    text = """Feature: foo
  @unit-test("a.py::test_x")
  Scenario: bar
    Given x

  @unit-test("a.py::test_z")
  Scenario: qux
"""
    pointers = _extract_tag_pointers(text, "bar")
    assert pointers == ["a.py::test_x"]


def test_extract_tag_pointers_with_other_scenarios_above() -> None:
    """A scenario with the same name across two features — but
    in a single file, the pointer resolves to the FIRST match."""
    text = """Feature: foo
  @unit-test("a.py::test_x")
  Scenario: bar
    Given x

  @unit-test("a.py::test_z")
  Scenario: bar
    Given y
"""
    pointers = _extract_tag_pointers(text, "bar")
    assert pointers == ["a.py::test_x"]


def test_legacy_extract_pointer_still_works() -> None:
    doc = "# See unit test test_cli.py::test_main_returns_one_on_workflow_not_found"
    assert _extract_pointer(doc) == "test_cli.py::test_main_returns_one_on_workflow_not_found"


def test_assert_pointer_resolves_accepts_bare_filename() -> None:
    """A pointer with no `::` is treated as a bare filename."""
    assert_pointer_resolves("test_cli.py")


def test_assert_pointer_resolves_accepts_function_pointer() -> None:
    """A pointer with `::` resolves to a real test function."""
    assert_pointer_resolves("test_cli.py::test_main_returns_zero_on_success")


def test_assert_pointer_resolves_strips_parametrize() -> None:
    """Parametrize suffix `[...]` is stripped before lookup."""
    assert_pointer_resolves("test_cli.py::test_main_returns_zero_on_success[x]")


def test_assert_pointer_resolves_rejects_missing_file() -> None:
    with pytest.raises(AssertionError, match="does not exist"):
        assert_pointer_resolves("test_does_not_exist.py")


def test_assert_pointer_resolves_rejects_missing_test() -> None:
    with pytest.raises(AssertionError, match="not found"):
        assert_pointer_resolves("test_cli.py::test_nonexistent_test")
