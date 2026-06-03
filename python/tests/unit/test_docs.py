from __future__ import annotations

import re
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"
CONFORMANCE = DOCS_DIR / "CONFORMANCE.md"
LOGGING = DOCS_DIR / "logging.md"
TOKEN_ACCOUNTING = DOCS_DIR / "token_accounting.md"


def test_docs_dir_exists() -> None:
    assert DOCS_DIR.is_dir()


def test_conformance_md_exists_and_is_substantial() -> None:
    """CONFORMANCE.md maps every §17 bullet to a test; it should
    be at least 1 KB and reference every §17 section."""
    assert CONFORMANCE.is_file()
    text = CONFORMANCE.read_text()
    assert len(text) > 1000
    for section in (
        "§17.1",
        "§17.2",
        "§17.3",
        "§17.4",
        "§17.5",
        "§17.6",
        "§17.7",
    ):
        assert section in text, f"missing section {section!r} in CONFORMANCE.md"


def test_logging_md_exists_and_mentions_required_fields() -> None:
    assert LOGGING.is_file()
    text = LOGGING.read_text()
    for required in (
        "issue_id",
        "issue_identifier",
        "session_id",
        "KvFormatter",
        "api_key",
        "forbidden",
    ):
        assert required in text, f"missing keyword {required!r} in logging.md"


def test_logging_md_lists_forbidden_fields() -> None:
    text = LOGGING.read_text()
    for forbidden in ("api_key", "password", "secret", "token"):
        assert forbidden.lower() in text.lower()


def test_token_accounting_md_exists_and_explains_absolute_rule() -> None:
    assert TOKEN_ACCOUNTING.is_file()
    text = TOKEN_ACCOUNTING.read_text()
    # The first rule: "last_token_usage" is ignored as a cumulative.
    assert "last_token_usage" in text
    assert "absolute" in text.lower()
    # The author of cumulative totals is documented.
    assert "total" in text.lower()
    # The implementation map references the Python modules.
    assert "symphony.observability.snapshot" in text
    assert "symphony.orchestrator.service" in text


def test_conformance_md_references_real_test_files() -> None:
    """Every test path mentioned in CONFORMANCE.md must exist."""
    text = CONFORMANCE.read_text()
    test_files = set(re.findall(r"test_[A-Za-z_]+\.py", text))
    for test_file in test_files:
        in_unit = (Path(__file__).resolve().parents[1] / "unit" / test_file).is_file()
        in_steps = (Path(__file__).resolve().parents[1] / "steps" / test_file).is_file()
        assert in_unit or in_steps, f"CONFORMANCE.md references {test_file} but file is missing"


def test_every_bdd_feature_has_a_pointer_in_conformance() -> None:
    """Every BDD feature file is listed in CONFORMANCE.md."""
    text = CONFORMANCE.read_text()
    features_dir = Path(__file__).resolve().parents[1] / "features"
    for feature in features_dir.glob("*.feature"):
        assert feature.name in text, f"feature {feature.name} is not mentioned in CONFORMANCE.md"
