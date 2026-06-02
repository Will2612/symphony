"""WORKFLOW.md loader: read, split, parse.

A `WORKFLOW.md` is a Markdown file with optional YAML front-matter
delimited by `---` lines. The loader:

1. Reads the file (raises `WorkflowMissingFile` if absent).
2. Strips a leading BOM if present.
3. Splits on the first two `---` lines; everything between is
   parsed as YAML, everything after is the body.
4. Requires the front-matter to be a YAML mapping; a non-mapping
   yields `WorkflowFrontMatterNotAMap`.
5. Returns a `Workflow` value with `front_matter`, `body`, `raw`,
   and `source`.

YAML parse failures surface as `WorkflowParseError`. Unterminated
front-matter also yields `WorkflowParseError`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from symphony.errors import (
    WorkflowFrontMatterNotAMap,
    WorkflowMissingFile,
    WorkflowParseError,
)

FRONT_MATTER_DELIMITER = "---"
_BOM = "\ufeff"


@dataclass(frozen=True)
class Workflow:
    """A loaded WORKFLOW.md value."""

    front_matter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    raw: str = ""
    source: Path | None = None


def load(path: str | Path) -> Workflow:
    """Load a `WORKFLOW.md` from disk.

    Raises:
        WorkflowMissingFile: the file is absent.
        WorkflowParseError: the front-matter is unterminated or the
            YAML is malformed.
        WorkflowFrontMatterNotAMap: the front-matter parsed but
            isn't a mapping.
    """
    p = Path(path)
    if not p.exists():
        raise WorkflowMissingFile(f"WORKFLOW.md not found: {p}", code="workflow_missing_file")
    text = p.read_text(encoding="utf-8")
    return load_from_string(text, source=p)


def load_from_string(text: str, *, source: Path | None = None) -> Workflow:
    """Parse a `WORKFLOW.md` payload from a string.

    See `load` for the error contract.
    """
    raw = text
    if raw.startswith(_BOM):
        raw = raw[len(_BOM) :]

    front_matter: dict[str, Any] = {}
    body = raw

    if raw.lstrip().startswith(FRONT_MATTER_DELIMITER):
        # Find the first newline after the leading delimiter
        first_nl = raw.find("\n")
        if first_nl == -1:
            raise WorkflowParseError(
                "unterminated front-matter: file is a single line",
                code="workflow_parse_error",
            )
        # The leading delimiter is on its own line
        leading = raw[:first_nl].strip()
        if leading == FRONT_MATTER_DELIMITER:
            rest = raw[first_nl + 1 :]
            # Find the closing delimiter
            close = _find_front_matter_close(rest)
            if close is None:
                raise WorkflowParseError(
                    "unterminated front-matter: missing closing '---'",
                    code="workflow_parse_error",
                )
            fm_end, after_close = close
            fm_text = rest[:fm_end]
            body = rest[after_close:]
            try:
                parsed = yaml.safe_load(fm_text)
            except yaml.YAMLError as exc:
                raise WorkflowParseError(
                    f"front-matter is not valid YAML: {exc}",
                    code="workflow_parse_error",
                ) from exc
            if parsed is None:
                front_matter = {}
            elif not isinstance(parsed, dict):
                raise WorkflowFrontMatterNotAMap(
                    f"front-matter must be a YAML mapping, got {type(parsed).__name__}",
                    code="workflow_front_matter_not_a_map",
                )
            else:
                front_matter = dict(parsed)
        else:
            # Leading line is not a delimiter — treat the whole text as body
            body = raw
    else:
        body = raw

    return Workflow(front_matter=front_matter, body=body, raw=text, source=source)


def _find_front_matter_close(rest: str) -> tuple[int, int] | None:
    """Find the boundary around the closing `---` line.

    Returns a tuple `(fm_end, after_close)` where `fm_end` is the
    index where the closing line begins and `after_close` is the
    index right after the newline that ends the closing line.

    Returns None if no close delimiter is found. The match must be on
    its own line, with optional trailing whitespace.
    """
    pos = 0
    while True:
        nl = rest.find("\n", pos)
        if nl == -1:
            if rest[pos:].rstrip("\r").strip() == FRONT_MATTER_DELIMITER:
                return (pos, len(rest))
            return None
        line = rest[pos:nl].rstrip("\r").strip()
        if line == FRONT_MATTER_DELIMITER:
            return (pos, nl + 1)
        pos = nl + 1
