"""BDD feature file conformance check.

Each feature file under `tests/features/` describes one SPEC §17
capability. The actual behavior is asserted by the unit tests
under `tests/unit/`; this test file is a no-op (no behavior
asserted at the BDD layer) — the actual assertions live in the
unit tests.

The feature files use the convention that each scenario carries
one or more `@unit-test("file.py::name")` tags pointing to the
unit test(s) that assert the scenario's behavior. This test
file walks every feature file in the suite, parses each
scenario, and asserts every `@unit-test` tag resolves to a real
test in the suite. A scenario whose pointer is missing or
broken is a conformance gap and fails the build.

Why this design:
- BDD scenarios are a SPEC §17 → unit-test pointer map (a
  documentation contract), not a behavior contract. The behavior
  is in the unit tests.
- pytest-bdd's wildcard step matching is brittle; this approach
  is simpler and gives the same coverage guarantee.
- The `_smoke.feature` file in this directory exists only to
  prove the BDD tooling is in place; it has no scenarios.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.steps._bdd_pointer import (
    _extract_tag_pointers,
    _parse_gherkin_scenarios,
    assert_pointer_resolves,
)

FEATURES_DIR = Path(__file__).resolve().parents[1] / "features"


def _iter_features() -> list[Path]:
    return sorted(FEATURES_DIR.glob("*.feature"))


def test_features_dir_exists() -> None:
    assert FEATURES_DIR.is_dir(), f"features dir missing: {FEATURES_DIR}"
    assert len(_iter_features()) >= 1


@pytest.mark.parametrize("feature", _iter_features(), ids=lambda p: p.name)
def test_feature_parses(feature: Path) -> None:
    """Each feature file must parse cleanly and have at least one
    scenario."""
    scenarios = _parse_gherkin_scenarios(feature.read_text())
    assert scenarios, f"no scenarios found in {feature.name}"


@pytest.mark.parametrize("feature", _iter_features(), ids=lambda p: p.name)
def test_every_scenario_has_at_least_one_unit_test_tag(feature: Path) -> None:
    """Every scenario in every feature file must have at least one
    `@unit-test("file.py::name")` tag."""
    raw = feature.read_text()
    scenarios = _parse_gherkin_scenarios(raw)
    for scenario_name in scenarios:
        pointers = _extract_tag_pointers(raw, scenario_name=scenario_name)
        assert pointers, (
            f"Scenario {scenario_name!r} in {feature.name} has no `@unit-test(...)` tag"
        )


@pytest.mark.parametrize("feature", _iter_features(), ids=lambda p: p.name)
def test_every_unit_test_pointer_resolves(feature: Path) -> None:
    """Every `@unit-test(...)` tag must point to a real test in the
    suite."""
    raw = feature.read_text()
    scenarios = _parse_gherkin_scenarios(raw)
    for scenario_name in scenarios:
        pointers = _extract_tag_pointers(raw, scenario_name=scenario_name)
        for ptr in pointers:
            assert_pointer_resolves(ptr)
