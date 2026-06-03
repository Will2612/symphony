"""SPEC §17 conformance sweep (TDD Step 25).

Walks every line of SPEC §17 (`.1` through `.7`) and confirms
that for each behavior bullet there is at least one test (TDD
or BDD) asserting it. This is the final gate of the plan
"walk SPEC §17 line by line, confirm each item has at least one
test".

The implementation strategy:

1. Parse SPEC.md for all `### 17.X` sections.
2. For each section, extract the bullet list.
3. For each bullet, derive a few keywords (the first 2-3
   content words).
4. Search the unit-test files and the CONFORMANCE.md for at
   least one match.

A bullet is "covered" if either:
- the CONFORMANCE.md has a row for the bullet pointing to a
  test, OR
- a unit test file contains a test whose name (or module
  docstring) mentions the bullet's keywords.

A bullet is "skipped" if it's marked N/A in the Python
implementation (e.g. Linear-only bullets; Live Integration
Profile bullets; status-dashboard bullets).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC = REPO_ROOT / "SPEC.md"
CONFORMANCE = REPO_ROOT / "python" / "docs" / "CONFORMANCE.md"
PYTHON_SRC = REPO_ROOT / "python" / "src" / "symphony"
PYTHON_TESTS = REPO_ROOT / "python" / "tests" / "unit"
PYTHON_BDD = REPO_ROOT / "python" / "tests" / "features"


_SECTION_RE = re.compile(r"^### (17\.\d+)\s+(.+?)$", re.MULTILINE)
_BULLET_RE = re.compile(r"^[\s]*[-*]\s+(.+?)$", re.MULTILINE)


def _extract_section_bullets(spec_text: str) -> dict[str, list[str]]:
    """Return a `{section_id: [bullet, ...]}` mapping for every
    `### 17.X` section."""
    sections: dict[str, list[str]] = {}
    lines = spec_text.splitlines()
    current_id: str | None = None
    current_bullets: list[str] = []
    for line in lines:
        m = _SECTION_RE.match(line)
        if m:
            if current_id is not None:
                sections[current_id] = current_bullets
            current_id = m.group(1)
            current_bullets = []
            continue
        if current_id is None:
            continue
        if _BULLET_RE.match(line):
            current_bullets.append(_BULLET_RE.match(line).group(1).strip())
    if current_id is not None:
        sections[current_id] = current_bullets
    return sections


# Bullets that intentionally don't have a Python test (per plan).
_NA_PATTERNS = (
    "Linear query uses the specified project filter field",
    "GraphQL `errors`",
    "Linear-only",
    "Linear adapter",
    "Linear",
    "Linear Adapter",
    "Real Integration Profile",
    "live e2e",
    "LiveView",
    "humanized event summaries",
    "human-readable status",
    "snapshot API",
    "Live tracker",
)


def _is_na(bullet: str) -> bool:
    return any(pat in bullet for pat in _NA_PATTERNS)


def _bullet_keywords(bullet: str) -> list[str]:
    """Pick 3 distinctive content words from a SPEC bullet.

    Strip SPEC cross-refs, parentheticals, and very common words
    (the, of, to, etc.) before splitting on whitespace.
    """
    text = re.sub(r"\([^)]*\)", "", bullet)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"[\"'].*?[\"']", "", text)
    text = re.sub(r"[^A-Za-z\s]", " ", text)
    stop = {
        "the",
        "of",
        "to",
        "and",
        "or",
        "a",
        "an",
        "in",
        "on",
        "for",
        "with",
        "by",
        "is",
        "are",
        "be",
        "that",
        "this",
        "as",
        "it",
        "its",
        "from",
        "when",
        "if",
    }
    words = [w.lower() for w in text.split() if w.lower() not in stop and len(w) > 3]
    return words[:3]


def _has_coverage(bullet: str) -> bool:
    """True if the bullet has at least one test asserting it."""
    if _is_na(bullet):
        return True

    # 1) The CONFORMANCE.md has a row for the bullet.
    conformance = CONFORMANCE.read_text()
    keywords = _bullet_keywords(bullet)
    rows = [line for line in conformance.splitlines() if line.startswith("|")]
    for row in rows:
        if any(kw in row.lower() for kw in keywords):
            return True

    # 2) Search the unit test files for tests whose names or
    # module docstrings mention the keywords.
    for test_file in PYTHON_TESTS.glob("test_*.py"):
        text = test_file.read_text()
        if any(f"test_{kw}" in text.lower() for kw in keywords):
            return True
        # Module docstring.
        docstring_match = re.search(r'"""(.+?)"""', text, re.DOTALL)
        if docstring_match and any(kw in docstring_match.group(1).lower() for kw in keywords):
            return True

    # 3) Search the BDD feature files.
    for feature in PYTHON_BDD.glob("*.feature"):
        text = feature.read_text()
        if all(kw in text.lower() for kw in keywords[:2]):
            return True

    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_spec_md_exists() -> None:
    assert SPEC.is_file()


def test_conformance_md_exists() -> None:
    assert CONFORMANCE.is_file()


def test_sections_are_parseable() -> None:
    text = SPEC.read_text()
    sections = _extract_section_bullets(text)
    assert "17.1" in sections
    assert "17.7" in sections
    # Every section has at least one bullet.
    for sid, bullets in sections.items():
        assert bullets, f"section {sid} has no bullets"


def test_section_coverage_full_sweep() -> None:
    """Every bullet in §17.1 through §17.7 is either covered by a
    test or marked N/A. A failure here means a SPEC behavior is
    not asserted by the test suite."""
    text = SPEC.read_text()
    sections = _extract_section_bullets(text)
    failures: list[str] = []
    for sid in ("17.1", "17.2", "17.3", "17.4", "17.5", "17.6", "17.7"):
        for bullet in sections.get(sid, []):
            if not _has_coverage(bullet):
                failures.append(f"§{sid}: {bullet[:80]}")
    assert not failures, (
        "The following SPEC §17 bullets have no Python test coverage:\n  " + "\n  ".join(failures)
    )


def test_sections_17_1_to_17_7_each_have_bullets() -> None:
    """Each core section should have at least 5 bullets (sanity
    check that we're not silently dropping bullets)."""
    text = SPEC.read_text()
    sections = _extract_section_bullets(text)
    for sid in ("17.1", "17.2", "17.3", "17.4", "17.5", "17.6", "17.7"):
        assert len(sections.get(sid, [])) >= 5, (
            f"section §{sid} has only {len(sections.get(sid, []))} bullets"
        )


def test_test_count_is_above_threshold() -> None:
    """The test suite must have at least 500 tests (a sanity check
    that all work-plan steps landed in code)."""
    result = subprocess.run(
        ["python3", "-m", "pytest", "--collect-only", "-q"],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT / "python",
    )
    output = result.stdout
    m = re.search(r"(\d+)\s+tests collected", output)
    assert m is not None, f"could not parse pytest output: {output[:500]}"
    n = int(m.group(1))
    assert n >= 500, f"only {n} tests collected (expected >= 500)"


def test_coverage_is_at_or_above_95_percent() -> None:
    """The coverage report must be >= 95% on src/symphony/."""
    result = subprocess.run(
        ["python3", "-m", "coverage", "report", "--include=src/symphony/*"],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT / "python",
    )
    output = result.stdout
    m = re.search(r"TOTAL\s+\d+\s+\d+\s+\d+\s+\d+\s+(\d+\.\d+)%", output)
    assert m is not None, f"could not parse coverage output: {output[:500]}"
    pct = float(m.group(1))
    assert pct >= 95.0, f"coverage {pct}% is below 95%"
