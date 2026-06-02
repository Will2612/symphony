"""Unit tests for `symphony.prompt.builder`.

Plan ref: §11 step 9, SPEC §5.4 + §5.5.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from symphony.errors import TemplateParseError, TemplateRenderError
from symphony.prompt.builder import (
    build_prompt,
    default_prompt,
    parse_template,
    render_template,
)


def _issue(**fields: Any) -> Mapping[str, Any]:
    return {
        "id": "ISSUE-1",
        "identifier": "ABC-1",
        "title": "Fix the thing",
        "description": "The thing is broken.",
        "state": "open",
        "labels": ["bug", "p1"],
        "blocked_by": ["ABC-0"],
    }


def test_build_prompt_renders_simple_template() -> None:
    out = build_prompt("Title: {{ issue.title }}", issue=_issue())
    assert out == "Title: Fix the thing"


def test_build_prompt_renders_attempt_variable() -> None:
    out = build_prompt("attempt={{ attempt }}", issue=_issue(), attempt=2)
    assert out == "attempt=2"


def test_build_prompt_attempt_is_none_on_first_attempt() -> None:
    out = build_prompt("attempt={{ attempt }}", issue=_issue())
    assert out == "attempt=None"


def test_build_prompt_iterates_labels() -> None:
    out = build_prompt(
        "{% for l in issue.labels %}[{{ l }}]{% endfor %}",
        issue=_issue(),
    )
    assert out == "[bug][p1]"


def test_build_prompt_falls_back_to_default_when_empty() -> None:
    out = build_prompt("", issue=_issue())
    assert "issue" in out.lower()  # default prompt mentions issue


def test_build_prompt_uses_fallback_when_only_whitespace() -> None:
    out = build_prompt("   \n\n  ", issue=_issue())
    assert "issue" in out.lower()


def test_build_prompt_unknown_variable_raises_render_error() -> None:
    with pytest.raises(TemplateRenderError):
        build_prompt("{{ issue.nope }}", issue=_issue())


def test_build_prompt_unknown_filter_raises_render_error() -> None:
    with pytest.raises(TemplateRenderError):
        build_prompt("{{ issue.title | nosuchfilter }}", issue=_issue())


def test_build_prompt_malformed_syntax_raises_parse_error() -> None:
    with pytest.raises(TemplateParseError):
        build_prompt("{{ issue.title", issue=_issue())


def test_build_prompt_iterates_blocked_by() -> None:
    out = build_prompt(
        "{% for b in issue.blocked_by %}{{ b }};{% endfor %}",
        issue=_issue(),
    )
    assert out == "ABC-0;"


def test_parse_template_returns_cached_template() -> None:
    t1 = parse_template("hello {{ issue.id }}")
    t2 = parse_template("hello {{ issue.id }}")
    # Same source string => equal rendering, but Jinja2 templates
    # are not value-equal; we test by rendering.
    assert t1.render(issue={"id": "X"}) == "hello X"
    assert t2.render(issue={"id": "X"}) == "hello X"


def test_parse_template_raises_on_syntax_error() -> None:
    with pytest.raises(TemplateParseError):
        parse_template("{{ unclosed")


def test_render_template_with_pre_parsed_template() -> None:
    t = parse_template("hi {{ issue.id }} attempt={{ attempt }}")
    out = render_template(t, issue={"id": "A"}, attempt=None)
    assert out == "hi A attempt=None"


def test_render_template_with_string() -> None:
    out = render_template("hi {{ issue.id }}", issue={"id": "A"}, attempt=0)
    assert out == "hi A"


def test_default_prompt_mentions_issue() -> None:
    assert "issue" in default_prompt().lower()


def test_build_prompt_supports_conditional() -> None:
    template = "{% if attempt %}retry={{ attempt }}{% else %}first{% endif %}"
    assert build_prompt(template, issue=_issue()) == "first"
    assert build_prompt(template, issue=_issue(), attempt=3) == "retry=3"


def test_build_prompt_stringifies_unknown_keys_gracefully() -> None:
    """A template accessing a non-existent path raises, but the issue
    object can include a numeric or list value; rendering must not
    crash on those."""
    out = build_prompt(
        "labels={{ issue.labels | length }}",
        issue=_issue(),
    )
    assert out == "labels=2"


def test_build_prompt_with_invalid_attribute_access_raises() -> None:
    """Accessing an attribute on a non-object raises TemplateRenderError."""
    # `issue.title` works (str); but calling a method that doesn't exist.
    with pytest.raises(TemplateRenderError):
        build_prompt("{{ issue.title.does_not_exist() }}", issue=_issue())


def test_render_template_with_python_type_error_raises_render_error() -> None:
    """A template that triggers a Python-level TypeError (e.g. from
    iterating a non-iterable) is surfaced as TemplateRenderError."""
    with pytest.raises(TemplateRenderError):
        render_template(
            "{% for i in 1 %}{{ i }}{% endfor %}",
            issue=_issue(),
            attempt=None,
        )
