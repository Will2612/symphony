"""Strict prompt template rendering.

Mirrors the Elixir `SymphonyElixir.PromptBuilder` module. Uses
Jinja2 with `StrictUndefined` so that any reference to an undefined
variable raises `TemplateRenderError`. Unknown filters also raise
`TemplateRenderError` (per SPEC §5.5: "unknown variable/filter,
invalid interpolation" → template_render_error).

Public API:

- `parse_template(source)`: parse a Jinja2 template; raise
  `TemplateParseError` on syntax errors and `TemplateRenderError`
  if any filter is unknown.
- `render_template(template, *, issue, attempt)`: render with the
  given issue and attempt.
- `build_prompt(source, *, issue, attempt)`: convenience that
  handles both the parse and render steps and applies the
  empty-prompt fallback.
- `default_prompt()`: the minimal default prompt used when the
  workflow body is empty.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any

import jinja2

from symphony.errors import TemplateParseError, TemplateRenderError

DEFAULT_PROMPT = (
    "You are working on an issue from a project tracker. "
    "Use the issue context below to drive your work.\n\n"
    "Issue: {{ issue.identifier }} — {{ issue.title }}\n"
    "Description:\n{{ issue.description }}\n"
)


def _get_env() -> jinja2.Environment:
    """Return a Jinja2 environment with strict undefined semantics.
    Cached at module level so we don't rebuild on every call."""
    env = globals().get("_ENV")
    if env is None:
        env = jinja2.Environment(
            undefined=jinja2.StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
        )
        globals()["_ENV"] = env
    return env


def _check_filters(env: jinja2.Environment, source: str) -> None:
    """Walk the parsed AST and raise `TemplateRenderError` for any
    filter that is not registered in the environment. Catches the
    common "no filter named X" error that Jinja2 would otherwise
    surface as `TemplateSyntaxError` at parse time."""
    ast = env.parse(source)  # let TemplateSyntaxError propagate
    try:
        filters = _find_filters(ast)
    except Exception:  # pragma: no cover - AST walk is total
        return  # defensive: never crash on filter introspection
    known = set(env.filters.keys())
    missing = [f for f in filters if f not in known]
    if missing:
        raise TemplateRenderError(
            f"template render error: unknown filter(s): {', '.join(sorted(missing))}",
            code="template_render_error",
        )


def _find_filters(ast: jinja2.nodes.Template) -> list[str]:
    """Recursively find all filter names used in the AST."""
    out: list[str] = []
    for node in ast.find_all(jinja2.nodes.Filter):
        out.append(node.name)
    return out


def parse_template(source: str) -> jinja2.Template:
    """Parse a Jinja2 template with `StrictUndefined`. Raises
    `TemplateParseError` on syntax errors and `TemplateRenderError`
    if any filter is unknown (per SPEC §5.5)."""
    env = _get_env()
    try:
        template = env.from_string(source)
    except jinja2.TemplateSyntaxError as e:
        # Distinguish "no filter named X" (a render-time concern
        # per SPEC §5.5) from real syntax errors.
        msg = (e.message or "").lower()
        if "no filter named" in msg:
            raise TemplateRenderError(
                f"template render error: {e.message} (line {e.lineno})",
                code="template_render_error",
            ) from e
        raise TemplateParseError(
            f"template parse error: {e.message} (line {e.lineno})",
            code="template_parse_error",
        ) from e
    # Defensive second pass: walk the AST to catch any filter names
    # that the parse step might have missed (e.g. dynamic filters).
    _check_filters(env, source)
    return template


def render_template(
    template: str | jinja2.Template,
    *,
    issue: Any,  # noqa: ANN401
    attempt: int | None,
) -> str:
    """Render `template` with `issue` and `attempt` in scope.

    Args:
        template: a Jinja2 source string or a pre-parsed
            `jinja2.Template` (from `parse_template`).
        issue: a mapping of issue fields.
        attempt: attempt number, or `None` for the first attempt.

    Raises:
        TemplateParseError: if `template` is a string and fails to parse.
        TemplateRenderError: if any variable is undefined, any filter
            is missing, or the runtime encounters any other render error.
    """
    compiled = parse_template(template) if isinstance(template, str) else template
    # Accept any Mapping-like, dataclass instance, or object with
    # `__dict__`; render via `dict(issue)` (works for Mappings and
    # objects whose `__iter__` yields key-value pairs) and fall
    # back to a dataclass-aware field extraction.
    if isinstance(issue, Mapping):
        issue_dict: dict[str, Any] = dict(issue)
    elif is_dataclass(issue):
        issue_dict = {f.name: getattr(issue, f.name) for f in fields(issue)}
    else:
        issue_dict = dict(vars(issue))
    try:
        return compiled.render(issue=issue_dict, attempt=attempt)
    except jinja2.UndefinedError as e:
        raise TemplateRenderError(
            f"template render error: {e.message}",
            code="template_render_error",
        ) from e
    except jinja2.exceptions.TemplateAssertionError as e:
        raise TemplateRenderError(
            f"template render error: {e.message}",
            code="template_render_error",
        ) from e
    except jinja2.TemplateError as e:
        raise TemplateRenderError(
            f"template render error: {e.message}",
            code="template_render_error",
        ) from e
    except Exception as e:  # any template body exception
        # A template body that triggers a Python-level error (e.g.
        # `TypeError` from iterating a non-iterable) is still a
        # template failure, not a runtime bug; surface it as such.
        raise TemplateRenderError(
            f"template render error: {type(e).__name__}: {e}",
            code="template_render_error",
        ) from e


def build_prompt(
    source: str,
    *,
    issue: Mapping[str, Any],
    attempt: int | None = None,
) -> str:
    """Build a prompt from `source`, applying the empty-prompt fallback
    per SPEC §5.4. Raises `TemplateParseError` / `TemplateRenderError`
    on bad input.

    If `source` is empty or whitespace-only, the default prompt is
    used and rendered instead.
    """
    body = source.strip()
    if not body:
        body = default_prompt()
    return render_template(body, issue=issue, attempt=attempt)


def default_prompt() -> str:
    """Return the minimal default prompt used when the workflow
    body is empty (SPEC §5.4)."""
    return DEFAULT_PROMPT


__all__ = [
    "build_prompt",
    "default_prompt",
    "parse_template",
    "render_template",
]
