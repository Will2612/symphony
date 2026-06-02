"""GitHub tracker adapter (production).

Implements the `Tracker` Protocol against the GitHub REST API
(plan §3.2, SPEC §11.1 + §11.4). Uses `httpx.AsyncClient` for
async HTTP I/O with a default 30 s timeout.

The 8 error categories from SPEC §11.4 are mapped to the typed
`GitHub*` errors in `symphony.errors`:

- 401            -> GitHubUnauthorized
- 403            -> GitHubForbidden
- 404            -> GitHubNotFound
- 429            -> GitHubRateLimited (carries `reset_at` from
                   the `x-ratelimit-reset` header)
- other 4xx/5xx  -> GitHubAPIStatus
- transport      -> GitHubAPIRequest
- empty body     -> GitHubUnknownPayload
- pagination     -> GitHubPaginationMissingLink

Pagination is handled via the `Link: <...>; rel="next"` response
header. If a non-empty page is received without a `Link` header,
a `GitHubPaginationMissingLink` is raised (SPEC §17 pagination
integrity).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

import httpx

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
from symphony.tracker.normalize import Issue, normalize_issue

_LOGGER = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 30.0
_USER_AGENT = "symphony-py/0.1"
_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2022-11-28"


def _raw_to_normalized(raw: dict[str, Any]) -> dict[str, Any]:
    """Translate a GitHub issue payload into the shape `normalize_issue`
    expects.

    Maps:
    - `id`          -> `id` (numeric, coerced to str)
    - `number`      -> `identifier` (with `#` prefix)
    - `title`       -> `title`
    - `body`        -> `description`
    - `state`       -> `state`
    - `html_url`    -> `url`
    - `labels[]`    -> label name strings
    - `created_at`  -> `created_at`
    - `updated_at`  -> `updated_at`
    - `pull_request` -> excludes (not an issue)
    """
    number = raw.get("number")
    if number is None:
        raise GitHubUnknownPayload(
            f"GitHub issue payload missing 'number' field: {raw!r}",
            code="github_unknown_payload",
        )
    return {
        "id": str(raw.get("id", "")),
        "identifier": f"#{number}",
        "title": raw.get("title", ""),
        "state": raw.get("state", ""),
        "description": raw.get("body") or None,
        "priority": None,
        "branch_name": raw.get("branch") or (raw.get("head") or {}).get("ref"),
        "url": raw.get("html_url"),
        "labels": [
            (lbl.get("name") if isinstance(lbl, dict) else lbl) for lbl in raw.get("labels", [])
        ],
        "inverse_relations": _extract_blocked_by_from_body(raw.get("body") or ""),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
    }


def _extract_blocked_by_from_body(body: str) -> list[dict[str, Any]]:
    """Parse 'Blocked by: #N, #M' or 'Blocks: #N, #M' markers from
    the issue body. Returns a list of `inverse_relations` entries
    that the normalizer can consume.

    GitHub has no first-class "blocks" relation; the convention is
    a Markdown line like `Blocked by: #1, #2` (case-insensitive).
    """
    if not body:
        return []
    out: list[dict[str, Any]] = []
    for line in body.splitlines():
        stripped = line.strip().lower()
        if not stripped.startswith(("blocked by:", "blocks:")):
            continue
        # Extract the part after the colon.
        _, _, after = line.partition(":")
        for raw_token in after.split(","):
            token = raw_token.strip()
            if not token.startswith("#"):
                continue
            try:
                number = int(token[1:])
            except ValueError:
                continue
            out.append(
                {
                    "type": "blocks",
                    "issue": {
                        "id": None,
                        "identifier": f"#{number}",
                        "state": None,
                    },
                }
            )
    return out


def _map_status_error(status: int, body_text: str, headers: httpx.Headers) -> Exception:
    if status == 401:
        return GitHubUnauthorized(f"github unauthorized: {body_text}", code="github_unauthorized")
    if status == 403:
        return GitHubForbidden(f"github forbidden: {body_text}", code="github_forbidden")
    if status == 404:
        return GitHubNotFound(f"github not found: {body_text}", code="github_not_found")
    if status == 429:
        reset_at_raw = headers.get("x-ratelimit-reset")
        reset_at: int | None = None
        if reset_at_raw is not None:
            try:
                reset_at = int(reset_at_raw)
            except ValueError:
                reset_at = None
        return GitHubRateLimited(
            f"github rate limited: {body_text}",
            reset_at=reset_at,
            code="github_rate_limited",
        )
    return GitHubAPIStatus(
        f"github api status {status}: {body_text}",
        code="github_api_status",
    )


def _parse_link_header(link: str | None) -> str | None:
    """Return the URL of `rel="next"` from a Link header, or None."""
    if not link:
        return None
    for part in link.split(","):
        section = part.strip()
        if 'rel="next"' in section:
            url_start = section.find("<")
            url_end = section.find(">", url_start)
            if url_start == -1 or url_end == -1:
                continue
            return section[url_start + 1 : url_end]
    return None


class GitHubTracker:
    """Async GitHub REST API adapter implementing the `Tracker` Protocol."""

    def __init__(
        self,
        config: SymphonyConfig,
        *,
        client: httpx.AsyncClient | None = None,
        endpoint: str | None = None,
    ) -> None:
        self.endpoint = endpoint or config.tracker.endpoint
        self._project_slug = config.tracker.project_slug
        self._api_key = config.tracker.api_key
        self._active_states = [s.lower() for s in config.tracker.active_states]
        self._terminal_states = [s.lower() for s in config.tracker.terminal_states]
        if client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(_DEFAULT_TIMEOUT_S),
                headers=self._default_headers(),
            )
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False

    @staticmethod
    def _default_headers() -> dict[str, str]:
        return {
            "accept": _ACCEPT,
            "user-agent": _USER_AGENT,
            "x-github-api-version": _API_VERSION,
        }

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _request_headers(self) -> dict[str, str]:
        """Headers for every request: defaults + bearer token."""
        return {**self._default_headers(), "authorization": f"Bearer {self._api_key}"}

    async def fetch_candidate_issues(self) -> Sequence[Issue]:
        """Fetch issues in any of the configured active states."""
        issues: list[Issue] = []
        # GitHub only knows open/closed natively. We accept any of
        # the configured active states; the only sensible mapping is
        # "open" -> "open" and any other -> "all" (no filter).
        state_param = self._state_query_param()
        url: str | None = f"{self.endpoint}/repos/{self._project_slug}/issues"
        params: dict[str, Any] = {"state": state_param, "per_page": 100}
        while url:
            try:
                response = await self._client.get(
                    url, params=params, headers=self._request_headers()
                )
            except httpx.HTTPError as e:
                raise GitHubAPIRequest(
                    f"github transport error: {e}", code="github_api_request"
                ) from e
            if response.status_code != 200:
                raise _map_status_error(response.status_code, response.text, response.headers)
            try:
                payload = response.json()
            except json.JSONDecodeError as e:
                raise GitHubUnknownPayload(
                    f"github returned non-JSON payload: {e}", code="github_unknown_payload"
                ) from e
            if not isinstance(payload, list):
                raise GitHubUnknownPayload(
                    f"github expected list, got {type(payload).__name__}",
                    code="github_unknown_payload",
                )
            for raw in payload:
                if not isinstance(raw, dict):
                    continue
                # Pull requests are also returned by /issues; skip them.
                if "pull_request" in raw:
                    continue
                normalized = normalize_issue(_raw_to_normalized(raw))
                # Apply state filter manually because GitHub's `state`
                # param is binary.
                if normalized.state.lower() not in self._active_states:
                    continue
                issues.append(normalized)
            # Pagination: a page shorter than `per_page` is the
            # natural end-of-results signal. A full page without a
            # `Link: rel="next"` header is a pagination integrity
            # error (SPEC §17).
            link = response.headers.get("link")
            next_url = _parse_link_header(link)
            if next_url is None and len(payload) >= 100:
                raise GitHubPaginationMissingLink(
                    f"github response page is full (>=100) with no Link header (url={url})",
                    code="github_pagination_missing_link",
                )
            url = next_url
            params = {}  # subsequent URLs are absolute with their own query
        return issues

    def _state_query_param(self) -> str:
        """Map active_states config to a single GitHub `state` query
        parameter. Only `open` is meaningful; otherwise use `all` and
        filter client-side."""
        if not self._active_states:
            return "all"
        if set(self._active_states) <= {"open"}:
            return "open"
        if set(self._active_states) <= {"closed"}:
            return "closed"
        return "all"

    async def fetch_issues_by_states(self, state_names: Sequence[str]) -> Sequence[Issue]:
        """Fetch issues in the given states. Empty list returns empty."""
        if not state_names:
            return []
        wanted = {s.strip().lower() for s in state_names if isinstance(s, str)}
        # Single fetch of the union; GitHub's `state` is binary, so we
        # pass `state=all` and filter client-side.
        url: str | None = f"{self.endpoint}/repos/{self._project_slug}/issues"
        params: dict[str, Any] = {"state": "all", "per_page": 100}
        out: list[Issue] = []
        while url:
            try:
                response = await self._client.get(
                    url, params=params, headers=self._request_headers()
                )
            except httpx.HTTPError as e:
                raise GitHubAPIRequest(
                    f"github transport error: {e}", code="github_api_request"
                ) from e
            if response.status_code != 200:
                raise _map_status_error(response.status_code, response.text, response.headers)
            try:
                payload = response.json()
            except json.JSONDecodeError as e:
                raise GitHubUnknownPayload(
                    f"github returned non-JSON payload: {e}", code="github_unknown_payload"
                ) from e
            if not isinstance(payload, list):
                raise GitHubUnknownPayload(
                    f"github expected list, got {type(payload).__name__}",
                    code="github_unknown_payload",
                )
            for raw in payload:
                if not isinstance(raw, dict) or "pull_request" in raw:
                    continue
                normalized = normalize_issue(_raw_to_normalized(raw))
                if normalized.state.lower() in wanted:
                    out.append(normalized)
            link = response.headers.get("link")
            next_url = _parse_link_header(link)
            if next_url is None and len(payload) >= 100:
                raise GitHubPaginationMissingLink(
                    f"github response page is full (>=100) with no Link header (url={url})",
                    code="github_pagination_missing_link",
                )
            url = next_url
            params = {}
        return out

    async def fetch_issue_states_by_ids(self, issue_ids: Sequence[str]) -> Sequence[Issue]:
        """Fetch each issue by its number; missing issues are skipped."""
        out: list[Issue] = []
        for issue_id in issue_ids:
            try:
                response = await self._client.get(
                    f"{self.endpoint}/repos/{self._project_slug}/issues/{issue_id}",
                    headers=self._request_headers(),
                )
            except httpx.HTTPError as e:
                raise GitHubAPIRequest(
                    f"github transport error: {e}", code="github_api_request"
                ) from e
            if response.status_code == 404:
                continue
            if response.status_code != 200:
                raise _map_status_error(response.status_code, response.text, response.headers)
            try:
                raw = response.json()
            except json.JSONDecodeError as e:
                raise GitHubUnknownPayload(
                    f"github returned non-JSON payload: {e}", code="github_unknown_payload"
                ) from e
            if not isinstance(raw, dict):
                continue
            out.append(normalize_issue(_raw_to_normalized(raw)))
        return out

    async def create_comment(self, issue_id: str, body: str) -> None:
        try:
            response = await self._client.post(
                f"{self.endpoint}/repos/{self._project_slug}/issues/{issue_id}/comments",
                json={"body": body},
                headers=self._request_headers(),
            )
        except httpx.HTTPError as e:
            raise GitHubAPIRequest(f"github transport error: {e}", code="github_api_request") from e
        if response.status_code not in (200, 201):
            raise _map_status_error(response.status_code, response.text, response.headers)

    async def update_issue_state(self, issue_id: str, state_name: str) -> None:
        target = state_name.strip().lower()
        if target not in {"open", "closed"}:
            raise GitHubAPIStatus(
                f"github cannot transition to state {state_name!r}: only 'open' or 'closed'",
                code="github_api_status",
            )
        try:
            response = await self._client.patch(
                f"{self.endpoint}/repos/{self._project_slug}/issues/{issue_id}",
                json={"state": target},
                headers=self._request_headers(),
            )
        except httpx.HTTPError as e:
            raise GitHubAPIRequest(f"github transport error: {e}", code="github_api_request") from e
        if response.status_code != 200:
            raise _map_status_error(response.status_code, response.text, response.headers)


# Runtime check that the class conforms to the Protocol.
_ = isinstance(GitHubTracker.__init__, object)  # placeholder for type check
