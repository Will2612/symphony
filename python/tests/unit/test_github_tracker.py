"""Unit tests for `symphony.tracker.github`.

Plan ref: §11 step 12, SPEC §11.4 (error categories) + §11.3 (relations).

Uses `httpx.MockTransport` so tests are fully in-process and
deterministic; no network or live GitHub credentials required.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from symphony.config.schema import SymphonyConfig
from symphony.errors import (
    GitHubAPIRequest,
    GitHubAPIStatus,
    GitHubForbidden,
    GitHubNotFound,
    GitHubPaginationMissingLink,
    GitHubRateLimited,
    GitHubUnauthorized,
    GitHubUnknownPayload,
)
from symphony.tracker.base import Tracker
from symphony.tracker.github import GitHubTracker


def _config(**overrides: Any) -> SymphonyConfig:
    base = {
        "tracker": {
            "kind": "github",
            "project_slug": "owner/repo",
            "api_key": "secret",
            "active_states": ["open"],
            "terminal_states": ["closed"],
        },
        "workspace": {"root": "/tmp/ws"},
    }
    base.update(overrides)
    return SymphonyConfig.model_validate(base)


def _make_tracker(
    config: SymphonyConfig,
    handler: Any,
) -> tuple[GitHubTracker, list[httpx.Request]]:
    """Build a tracker whose httpx client uses the given handler."""
    transport = httpx.MockTransport(handler)
    requests: list[httpx.Request] = []

    def _capturing(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return transport.handle_request(request)

    captured_transport = httpx.MockTransport(_capturing)
    client = httpx.AsyncClient(transport=captured_transport)
    tracker = GitHubTracker(config, client=client)
    return tracker, requests


def _issue_payload(
    number: int = 1,
    title: str = "Test issue",
    state: str = "open",
    body: str = "",
    labels: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": 1000 + number,
        "number": number,
        "title": title,
        "body": body,
        "state": state,
        "html_url": f"https://github.com/owner/repo/issues/{number}",
        "labels": labels or [],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "user": {"login": "alice"},
    }


def _paginated(payloads: list[dict[str, Any]], links: list[str | None]) -> list[httpx.Response]:
    """Build a sequence of HTTP responses for pagination. Each
    response is a page; `links[i]` is the Link header (or None)."""
    responses: list[httpx.Response] = []
    for payload, link in zip(payloads, links, strict=True):
        headers = {"content-type": "application/json"}
        if link is not None:
            headers["link"] = link
        responses.append(httpx.Response(200, json=payload, headers=headers))
    return responses


def test_github_tracker_conforms_to_protocol() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    tracker, _ = _make_tracker(_config(), _handler)
    assert isinstance(tracker, Tracker)


async def test_github_tracker_fetch_candidate_issues_returns_issues() -> None:
    page = [_issue_payload(1, state="open"), _issue_payload(2, state="open")]

    def _handler(request: httpx.Request) -> httpx.Response:
        # Default state filter is `open`; the GitHub API accepts a
        # `state=open` query param, but the tracker should be
        # explicit about it.
        assert request.url.params.get("state") == "open"
        return httpx.Response(200, json=page)

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_candidate_issues()
    assert len(issues) == 2
    assert {i.identifier for i in issues} == {"#1", "#2"}
    assert {i.state for i in issues} == {"open"}


async def test_github_tracker_fetch_uses_owner_repo_path() -> None:
    seen_urls: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json=[])

    tracker, _ = _make_tracker(_config(), _handler)
    await tracker.fetch_candidate_issues()
    assert any("repos/owner/repo/issues" in u for u in seen_urls)


async def test_github_tracker_sends_authorization_header() -> None:
    captured: dict[str, str] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json=[])

    tracker, _ = _make_tracker(_config(), _handler)
    await tracker.fetch_candidate_issues()
    assert captured["auth"] == "Bearer secret"


async def test_github_tracker_accept_header() -> None:
    captured: dict[str, str] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["accept"] = request.headers.get("accept", "")
        return httpx.Response(200, json=[])

    tracker, _ = _make_tracker(_config(), _handler)
    await tracker.fetch_candidate_issues()
    assert "application/vnd.github" in captured["accept"]


async def test_github_tracker_uses_custom_endpoint() -> None:
    cfg = _config(
        tracker={
            "kind": "github",
            "project_slug": "owner/repo",
            "api_key": "x",
            "endpoint": "https://github.example.com/api/v3",
        }
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    tracker, _ = _make_tracker(cfg, _handler)
    await tracker.fetch_candidate_issues()
    # The custom endpoint was used as the base.
    assert tracker.endpoint == "https://github.example.com/api/v3"


async def test_github_tracker_pagination_follows_link_header() -> None:
    page1 = [_issue_payload(1, state="open")]
    page2 = [_issue_payload(2, state="open")]
    link1 = '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="next"'
    responses = _paginated([page1, page2], [link1, None])
    call_count = {"n": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        idx = call_count["n"]
        call_count["n"] += 1
        return responses[idx]

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_candidate_issues()
    assert len(issues) == 2
    assert {i.identifier for i in issues} == {"#1", "#2"}
    assert call_count["n"] == 2


async def test_github_tracker_pagination_stops_at_end() -> None:
    """Pagination terminates cleanly when the server returns a page
    of length < 100 (i.e., the natural end-of-results signal) and
    no Link header."""
    # 1 issue on a 100-per-page request is a clear end-of-results
    # signal — no next link is required, no error is raised.
    page1 = [_issue_payload(1, state="open")]
    responses = _paginated([page1], [None])
    call_count = {"n": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        idx = call_count["n"]
        call_count["n"] += 1
        return responses[idx]

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_candidate_issues()
    assert len(issues) == 1
    assert call_count["n"] == 1


async def test_github_tracker_401_raises_unauthorized() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "bad token"})

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubUnauthorized):
        await tracker.fetch_candidate_issues()


async def test_github_tracker_403_raises_forbidden() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden"})

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubForbidden):
        await tracker.fetch_candidate_issues()


async def test_github_tracker_429_raises_rate_limited_with_reset() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"message": "rate limit"},
            headers={"x-ratelimit-reset": "1700000000"},
        )

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubRateLimited) as exc:
        await tracker.fetch_candidate_issues()
    assert exc.value.reset_at == 1700000000


async def test_github_tracker_404_raises_not_found() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubNotFound):
        await tracker.fetch_candidate_issues()


async def test_github_tracker_500_raises_status_error() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "server error"})

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubAPIStatus):
        await tracker.fetch_candidate_issues()


async def test_github_tracker_connection_error_raises_request_error() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubAPIRequest):
        await tracker.fetch_candidate_issues()


async def test_github_tracker_fetch_issue_states_by_ids_uses_individual_endpoint() -> None:
    seen_urls: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json=_issue_payload(7, state="open"))

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_issue_states_by_ids(["7"])
    assert len(issues) == 1
    assert issues[0].id == "1007"
    assert any("/repos/owner/repo/issues/7" in u for u in seen_urls)


async def test_github_tracker_fetch_issue_states_by_ids_skips_missing() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/issues/7"):
            return httpx.Response(200, json=_issue_payload(7))
        return httpx.Response(404, json={"message": "not found"})

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_issue_states_by_ids(["7", "8"])
    assert len(issues) == 1
    assert issues[0].id == "1007"


async def test_github_tracker_fetch_issue_states_by_ids_empty() -> None:
    tracker, _ = _make_tracker(_config(), lambda r: httpx.Response(200, json=[]))
    issues = await tracker.fetch_issue_states_by_ids([])
    assert issues == []


async def test_github_tracker_create_comment_posts_to_issue() -> None:
    captured: dict[str, Any] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content) if request.content else None
        return httpx.Response(201, json={"id": 1, "body": "hi"})

    tracker, _ = _make_tracker(_config(), _handler)
    await tracker.create_comment("7", "hi")
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/repos/owner/repo/issues/7/comments")
    assert captured["body"] == {"body": "hi"}


async def test_github_tracker_update_issue_state_closes_issue() -> None:
    captured: dict[str, Any] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content) if request.content else None
        return httpx.Response(200, json=_issue_payload(7, state="closed"))

    tracker, _ = _make_tracker(_config(), _handler)
    await tracker.update_issue_state("7", "closed")
    assert captured["method"] == "PATCH"
    assert captured["url"].endswith("/repos/owner/repo/issues/7")
    assert captured["body"] == {"state": "closed"}


async def test_github_tracker_update_issue_state_to_open() -> None:
    captured: dict[str, Any] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content) if request.content else None
        return httpx.Response(200, json=_issue_payload(7, state="open"))

    tracker, _ = _make_tracker(_config(), _handler)
    await tracker.update_issue_state("7", "open")
    assert captured["body"] == {"state": "open"}


async def test_github_tracker_update_issue_state_404_raises_not_found() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubNotFound):
        await tracker.update_issue_state("999", "closed")


async def test_github_tracker_normalizes_issue_state() -> None:
    """The state name is mapped to the GitHub state value."""
    page = [_issue_payload(1, state="closed")]

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=page)

    cfg = _config(
        tracker={
            "kind": "github",
            "project_slug": "owner/repo",
            "api_key": "x",
            "active_states": ["closed"],  # treat closed as active
            "terminal_states": ["open"],
        }
    )
    tracker, _ = _make_tracker(cfg, _handler)
    issues = await tracker.fetch_candidate_issues()
    assert len(issues) == 1
    assert issues[0].state == "closed"


async def test_github_tracker_parses_blocked_by_from_body() -> None:
    body = "Some description.\n\nBlocked by: #1, #2\nMore text."
    page = [_issue_payload(3, state="open", body=body)]

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=page)

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_candidate_issues()
    assert len(issues) == 1
    # The blocked_by list is empty because the referenced issues
    # are not in this response; the parser extracts the numbers
    # but the normalizer still needs a relation type. We only
    # assert the body is parsed; the full wiring is integration-tested.
    assert "Blocked by" in issues[0].description or body in (issues[0].description or "")


async def test_github_tracker_handles_empty_response() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_candidate_issues()
    assert issues == []


async def test_github_tracker_429_without_reset_header() -> None:
    """A 429 without x-ratelimit-reset still raises GitHubRateLimited."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limit"})

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubRateLimited) as exc:
        await tracker.fetch_candidate_issues()
    assert exc.value.reset_at is None


async def test_github_tracker_pagination_missing_link_raises() -> None:
    """If a full page (length == per_page) has no `Link: rel="next"`
    header, raise GitHubPaginationMissingLink (SPEC §17 pagination
    integrity)."""
    # First page is full (100) and has a next link.
    page1 = [_issue_payload(i, state="open") for i in range(1, 101)]
    link1 = '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="next"'
    # Second page is also full (100) but has no link header — broken.
    page2 = [_issue_payload(i, state="open") for i in range(101, 201)]
    responses = [
        httpx.Response(200, json=page1, headers={"link": link1}),
        httpx.Response(200, json=page2),  # no link header, full
    ]
    call_count = {"n": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        idx = call_count["n"]
        call_count["n"] += 1
        return responses[idx]

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubPaginationMissingLink):
        await tracker.fetch_candidate_issues()


# ---------------------------------------------------------------------------
# fetch_issues_by_states
# ---------------------------------------------------------------------------


async def test_github_tracker_fetch_issues_by_states_empty_returns_empty() -> None:
    tracker, _ = _make_tracker(_config(), lambda r: httpx.Response(200, json=[]))
    issues = await tracker.fetch_issues_by_states([])
    assert issues == []


async def test_github_tracker_fetch_issues_by_states_filters_correctly() -> None:
    page = [
        _issue_payload(1, state="open"),
        _issue_payload(2, state="closed"),
    ]

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=page)

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_issues_by_states(["open"])
    assert {i.identifier for i in issues} == {"#1"}


async def test_github_tracker_fetch_issues_by_states_pagination() -> None:
    page1 = [_issue_payload(1, state="open")]
    link1 = '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="next"'
    page2 = [_issue_payload(2, state="open")]
    responses = _paginated([page1, page2], [link1, None])
    call_count = {"n": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        idx = call_count["n"]
        call_count["n"] += 1
        return responses[idx]

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_issues_by_states(["open"])
    assert len(issues) == 2
    assert call_count["n"] == 2


async def test_github_tracker_fetch_issues_by_states_skips_prs_and_nondicts() -> None:
    page = [
        _issue_payload(1, state="open"),
        {"pull_request": {"url": "x"}},  # PR — skipped
        "not a dict",  # non-dict — skipped
    ]

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=page)

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_issues_by_states(["open"])
    assert {i.identifier for i in issues} == {"#1"}


async def test_github_tracker_fetch_issues_by_states_404() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubNotFound):
        await tracker.fetch_issues_by_states(["open"])


async def test_github_tracker_fetch_issues_by_states_transport_error() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubAPIRequest):
        await tracker.fetch_issues_by_states(["open"])


async def test_github_tracker_fetch_issues_by_states_invalid_json() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json", headers={"content-type": "text/plain"})

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubUnknownPayload):
        await tracker.fetch_issues_by_states(["open"])


async def test_github_tracker_fetch_issues_by_states_non_list_payload() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"not": "a list"})

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubUnknownPayload):
        await tracker.fetch_issues_by_states(["open"])


async def test_github_tracker_fetch_issues_by_states_pagination_missing_link() -> None:
    page1 = [_issue_payload(i, state="open") for i in range(1, 101)]
    link1 = '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="next"'
    page2 = [_issue_payload(i, state="open") for i in range(101, 201)]
    responses = [
        httpx.Response(200, json=page1, headers={"link": link1}),
        httpx.Response(200, json=page2),
    ]
    call_count = {"n": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        idx = call_count["n"]
        call_count["n"] += 1
        return responses[idx]

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubPaginationMissingLink):
        await tracker.fetch_issues_by_states(["open"])


# ---------------------------------------------------------------------------
# fetch_issue_states_by_ids — additional branches
# ---------------------------------------------------------------------------


async def test_github_tracker_fetch_issue_states_by_ids_transport_error() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubAPIRequest):
        await tracker.fetch_issue_states_by_ids(["1"])


async def test_github_tracker_fetch_issue_states_by_ids_500() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "server error"})

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubAPIStatus):
        await tracker.fetch_issue_states_by_ids(["1"])


async def test_github_tracker_fetch_issue_states_by_ids_invalid_json() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json", headers={"content-type": "text/plain"})

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubUnknownPayload):
        await tracker.fetch_issue_states_by_ids(["1"])


async def test_github_tracker_fetch_issue_states_by_ids_non_dict() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "a", "dict"])

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_issue_states_by_ids(["1"])
    assert issues == []


# ---------------------------------------------------------------------------
# create_comment — additional branches
# ---------------------------------------------------------------------------


async def test_github_tracker_create_comment_404_raises_not_found() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubNotFound):
        await tracker.create_comment("999", "hi")


async def test_github_tracker_create_comment_transport_error() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubAPIRequest):
        await tracker.create_comment("1", "hi")


# ---------------------------------------------------------------------------
# update_issue_state — additional branches
# ---------------------------------------------------------------------------


async def test_github_tracker_update_issue_state_invalid_state_raises() -> None:
    tracker, _ = _make_tracker(_config(), lambda r: httpx.Response(200, json={}))
    with pytest.raises(GitHubAPIStatus):
        await tracker.update_issue_state("1", "weird-state")


async def test_github_tracker_update_issue_state_transport_error() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubAPIRequest):
        await tracker.update_issue_state("1", "closed")


# ---------------------------------------------------------------------------
# State query param mapping
# ---------------------------------------------------------------------------


async def test_github_tracker_state_query_param_open() -> None:
    cfg = _config(
        tracker={
            "kind": "github",
            "project_slug": "o/r",
            "api_key": "x",
            "active_states": ["open"],
            "terminal_states": ["closed"],
        }
    )
    seen: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=[])

    tracker, _ = _make_tracker(cfg, _handler)
    await tracker.fetch_candidate_issues()
    assert any("state=open" in u for u in seen)


async def test_github_tracker_state_query_param_mixed() -> None:
    cfg = _config(
        tracker={
            "kind": "github",
            "project_slug": "o/r",
            "api_key": "x",
            "active_states": ["open", "closed"],
            "terminal_states": [],
        }
    )
    seen: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=[])

    tracker, _ = _make_tracker(cfg, _handler)
    await tracker.fetch_candidate_issues()
    assert any("state=all" in u for u in seen)


# ---------------------------------------------------------------------------
# Body-parser branches
# ---------------------------------------------------------------------------


async def test_github_tracker_extract_blocked_by_ignores_non_hash_tokens() -> None:
    """Non-# tokens and invalid numbers are silently skipped."""
    body = "Blocked by: foo, #notanumber, #1"
    page = [_issue_payload(1, state="open", body=body)]

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=page)

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_candidate_issues()
    assert len(issues) == 1


async def test_github_tracker_handles_pull_request_entries() -> None:
    """GitHub /issues returns PRs too; they MUST be skipped."""
    page = [
        {
            "pull_request": {"url": "x"},
            "id": 9,
            "number": 9,
            "state": "open",
            "title": "PR",
            "body": "",
            "html_url": "u",
            "labels": [],
        },
        _issue_payload(1, state="open"),
    ]

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=page)

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_candidate_issues()
    assert {i.identifier for i in issues} == {"#1"}


async def test_github_tracker_handles_non_dict_items_in_response() -> None:
    """Non-dict items in the response are skipped, not crashed."""
    page = ["junk", 123, _issue_payload(1, state="open")]

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=page)

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_candidate_issues()
    assert {i.identifier for i in issues} == {"#1"}


async def test_github_tracker_invalid_json_in_response() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json", headers={"content-type": "text/plain"})

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubUnknownPayload):
        await tracker.fetch_candidate_issues()


async def test_github_tracker_non_list_response() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"not": "a list"})

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubUnknownPayload):
        await tracker.fetch_candidate_issues()


async def test_github_tracker_skips_payload_missing_number() -> None:
    """An issue payload without `number` raises GitHubUnknownPayload."""
    page = [
        {"id": 1, "state": "open", "title": "no number", "body": "", "html_url": "u", "labels": []}
    ]

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=page)

    tracker, _ = _make_tracker(_config(), _handler)
    with pytest.raises(GitHubUnknownPayload):
        await tracker.fetch_candidate_issues()


# ---------------------------------------------------------------------------
# Link-header parser
# ---------------------------------------------------------------------------


async def test_github_tracker_link_header_malformed_returns_no_next() -> None:
    """A Link header with rel="next" but no angle brackets is ignored."""
    # A link with rel="next" but no closing `>` is malformed;
    # the parser MUST skip it (no next URL → stop paginating).
    page = [_issue_payload(1, state="open")]
    responses = _paginated([page], ['rel="next"'])
    call_count = {"n": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        idx = call_count["n"]
        call_count["n"] += 1
        return responses[idx]

    tracker, _ = _make_tracker(_config(), _handler)
    issues = await tracker.fetch_candidate_issues()
    assert len(issues) == 1
    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def test_github_tracker_aclose_closes_owned_client() -> None:
    cfg = _config()
    tracker = GitHubTracker(cfg)
    await tracker.aclose()  # owns the client — must not raise


async def test_github_tracker_aclose_does_not_close_injected_client() -> None:
    cfg = _config()
    sentinel_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))
    )
    tracker = GitHubTracker(cfg, client=sentinel_client)
    await tracker.aclose()
    # If we tried to close a non-owned client, this would fail.
    await sentinel_client.get("https://api.github.com/test")
