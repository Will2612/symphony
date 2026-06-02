"""Step definitions for the skeleton BDD feature.

This proves the pytest-bdd wiring is in place; real per-behavior
scenarios land in the work-plan steps.
"""

from __future__ import annotations

import pytest
from pytest_bdd import scenarios, then, when

import symphony

scenarios("../features/skeleton.feature")


@pytest.fixture
def imported_symphony() -> None:
    return None


@when("I import the symphony package")
def import_symphony() -> None:
    return None


@then("the version string is non-empty")
def version_string_is_non_empty() -> None:
    assert isinstance(symphony.__version__, str)
    assert symphony.__version__
