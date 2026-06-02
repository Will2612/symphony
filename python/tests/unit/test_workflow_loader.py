"""Unit tests for `symphony.workflow.loader`.

Plan ref: §11 step 3. Loads `WORKFLOW.md` from disk, splits YAML
front-matter from the Markdown body, parses the front-matter, and
returns a `Workflow` value (front-matter dict + body string + raw
text + source path).

Errors:

- `WorkflowMissingFile` (code: workflow_missing_file) when the file
  is absent.
- `WorkflowParseError` (code: workflow_parse_error) when YAML is
  malformed.
- `WorkflowFrontMatterNotAMap` (code: workflow_front_matter_not_a_map)
  when the front-matter is not a YAML mapping.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from symphony.errors import (
    WorkflowFrontMatterNotAMap,
    WorkflowMissingFile,
    WorkflowParseError,
)
from symphony.workflow.loader import (
    FRONT_MATTER_DELIMITER,
    Workflow,
    load,
    load_from_string,
)


def test_load_returns_a_workflow_value(tmp_path: Path) -> None:
    f = tmp_path / "WORKFLOW.md"
    f.write_text("---\nname: hello\n---\nbody text\n", encoding="utf-8")
    w = load(f)
    assert isinstance(w, Workflow)
    assert w.front_matter == {"name": "hello"}
    assert w.body == "body text\n"
    assert w.source == f


def test_load_from_string_basic() -> None:
    w = load_from_string("---\nname: hello\n---\nbody text\n", source=Path("x.md"))
    assert w.front_matter == {"name": "hello"}
    assert w.body == "body text\n"
    assert w.source == Path("x.md")


def test_load_from_string_handles_crlf() -> None:
    text = "---\r\nname: hello\r\n---\r\nbody\r\n"
    w = load_from_string(text, source=Path("x.md"))
    assert w.front_matter == {"name": "hello"}
    assert w.body == "body\r\n"


def test_load_from_string_handles_bom() -> None:
    text = "\ufeff---\nname: hello\n---\nbody\n"
    w = load_from_string(text, source=Path("x.md"))
    assert w.front_matter == {"name": "hello"}


def test_load_from_string_empty_body() -> None:
    w = load_from_string("---\nname: hello\n---\n", source=Path("x.md"))
    assert w.front_matter == {"name": "hello"}
    assert w.body == ""


def test_load_from_string_no_front_matter() -> None:
    w = load_from_string("just body text\n", source=Path("x.md"))
    assert w.front_matter == {}
    assert w.body == "just body text\n"


def test_load_from_string_unterminated_front_matter() -> None:
    with pytest.raises(WorkflowParseError):
        load_from_string("---\nname: hello\nno terminator\n", source=Path("x.md"))


def test_load_from_string_yaml_parse_error() -> None:
    with pytest.raises(WorkflowParseError):
        load_from_string("---\nname: : :\n---\nbody\n", source=Path("x.md"))


def test_load_from_string_front_matter_must_be_a_mapping() -> None:
    with pytest.raises(WorkflowFrontMatterNotAMap):
        load_from_string("---\n- a\n- b\n---\nbody\n", source=Path("x.md"))


def test_load_from_string_front_matter_must_not_be_a_scalar() -> None:
    with pytest.raises(WorkflowFrontMatterNotAMap):
        load_from_string("---\njust a string\n---\nbody\n", source=Path("x.md"))


def test_load_missing_file_raises(tmp_path: Path) -> None:
    f = tmp_path / "does-not-exist.md"
    with pytest.raises(WorkflowMissingFile):
        load(f)


def test_load_empty_file_raises(tmp_path: Path) -> None:
    f = tmp_path / "empty.md"
    f.write_text("", encoding="utf-8")
    w = load(f)
    assert w.front_matter == {}
    assert w.body == ""


def test_load_file_with_only_front_matter_terminator(tmp_path: Path) -> None:
    f = tmp_path / "minimal.md"
    f.write_text("---\n", encoding="utf-8")
    with pytest.raises(WorkflowParseError):
        load(f)


def test_load_file_with_only_dashes_no_newline(tmp_path: Path) -> None:
    f = tmp_path / "only-dashes.md"
    f.write_text("---", encoding="utf-8")
    with pytest.raises(WorkflowParseError):
        load(f)


def test_load_file_with_only_dashes_and_whitespace(tmp_path: Path) -> None:
    f = tmp_path / "only-dashes-ws.md"
    f.write_text("---   \n", encoding="utf-8")
    with pytest.raises(WorkflowParseError):
        load(f)


def test_load_front_matter_terminator_no_trailing_newline(tmp_path: Path) -> None:
    f = tmp_path / "no-trailing.md"
    f.write_text("---\nname: hello\n---\nbody", encoding="utf-8")
    w = load(f)
    assert w.front_matter == {"name": "hello"}
    assert w.body == "body"


def test_front_matter_delimiter_constant_is_dashes() -> None:
    assert FRONT_MATTER_DELIMITER == "---"
