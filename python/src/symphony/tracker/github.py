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
_ACCEPT_GQL = "application/vnd.github+json"
_API_VERSION = "2022-11-28"
_GRAPHQL_PATH = "/graphql"


def _raw_to_normalized(raw: dict[str, Any]) -> dict[str, Any]:
    """Translate a GitHub issue payload into the shape `normalize_issue`
    expects.

    Maps:
    - `id`          -> `id` (numeric, coerced to str)
    - `number`      -> `identifier` (with `#` prefix)
    - `title`       -> `title`
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


def _gql_issue_to_normalized(content: object) -> Issue | None:
    """Translate a GraphQL `ProjectV2Item.content` Issue payload into
    a normalized `Issue`.

    Returns `None` if the payload is not a usable Issue (e.g. PR,
    draft issue, or a content node missing a `number`).
    """
    if not content or not isinstance(content, dict):
        return None
    if content.get("__typename") not in (None, "Issue"):
        return None
    number = content.get("number")
    if number is None:
        return None
    labels_payload = content.get("labels") or {}
    label_nodes = labels_payload.get("nodes") if isinstance(labels_payload, dict) else None
    if label_nodes is None:
        label_nodes = []
    raw: dict[str, Any] = {
        "id": str(content.get("id") or ""),
        "identifier": f"#{number}",
        "title": content.get("title") or "",
        "state": (content.get("state") or "").lower(),
        "description": content.get("body") or None,
        "priority": None,
        "branch_name": None,
        "url": content.get("url"),
        "labels": [ln.get("name") for ln in label_nodes if isinstance(ln, dict) and ln.get("name")],
        "inverse_relations": _extract_blocked_by_from_body(content.get("body") or ""),
        "created_at": content.get("createdAt"),
        "updated_at": content.get("updatedAt"),
    }
    return normalize_issue(raw)


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
        self._project_number = config.tracker.project_number
        self._active_statuses = [s.lower() for s in config.tracker.active_statuses]
        if self._project_number:
            owner = self._project_slug.split("/", 1)[0] if self._project_slug else ""
            self._project_owner = owner
        else:
            self._project_owner = ""
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

    async def _post_graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """POST a GraphQL query to the configured GitHub endpoint.

        Returns the `data` field of the response, or raises the
        same `GitHub*` error types as REST calls on transport /
        HTTP / non-2xx / non-JSON responses. `errors` payloads are
        raised as `GitHubAPIStatus` with the first error message.
        """
        url = f"{self.endpoint}{_GRAPHQL_PATH}"
        body: dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables
        try:
            response = await self._client.post(url, json=body, headers=self._request_headers())
        except httpx.HTTPError as e:
            raise GitHubAPIRequest(f"github transport error: {e}", code="github_api_request") from e
        if response.status_code != 200:
            raise _map_status_error(response.status_code, response.text, response.headers)
        try:
            payload = response.json()
        except json.JSONDecodeError as e:
            raise GitHubUnknownPayload(
                f"github graphql returned non-JSON payload: {e}",
                code="github_unknown_payload",
            ) from e
        if not isinstance(payload, dict):
            raise GitHubUnknownPayload(
                f"github graphql expected object, got {type(payload).__name__}",
                code="github_unknown_payload",
            )
        errors = payload.get("errors")
        if errors:
            first = errors[0]
            msg = first.get("message") if isinstance(first, dict) else str(first)
            raise GitHubAPIStatus(f"github graphql error: {msg}", code="github_api_status")
        data: dict[str, Any] = payload.get("data")  # type: ignore[assignment]
        if not isinstance(data, dict):
            raise GitHubUnknownPayload(
                f"github graphql response missing 'data' object: {payload!r}",
                code="github_unknown_payload",
            )
        return data

    async def fetch_candidate_issues(self) -> Sequence[Issue]:
        """Fetch issues in any of the configured active states.

        When `tracker.project_number` is set, this routes through
        the Projects v2 GraphQL API and additionally filters by the
        issue's Status field value (`tracker.active_statuses`).
        When `project_number` is unset, the original REST path is
        used and the Status filter is skipped.
        """
        if self._project_number:
            return await self._fetch_candidate_issues_via_project()
        return await self._fetch_candidate_issues_via_rest()

    async def _fetch_candidate_issues_via_rest(self) -> Sequence[Issue]:
        """REST-based candidate fetch: only filters by `active_states`."""
        issues: list[Issue] = []
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
                if "pull_request" in raw:
                    continue
                normalized = normalize_issue(_raw_to_normalized(raw))
                if normalized.state.lower() not in self._active_states:
                    continue
                issues.append(normalized)
            link = response.headers.get("link")
            next_url = _parse_link_header(link)
            if next_url is None and len(payload) >= 100:
                raise GitHubPaginationMissingLink(
                    f"github response page is full (>=100) with no Link header (url={url})",
                    code="github_pagination_missing_link",
                )
            url = next_url
            params = {}
        return issues

    async def _fetch_candidate_issues_via_project(self) -> Sequence[Issue]:
        """GraphQL-based candidate fetch via the linked Projects v2 board.

        Fetches items belonging to the configured project number
        (under the repo's owner) and keeps only those whose content
        is an Issue, whose GitHub state is in `active_states`, and
        whose project Status field value is in `active_statuses`.
        Issues with no Status value (missing field value) are
        skipped when `active_statuses` is non-empty.
        """
        assert self._project_number is not None
        if not self._project_owner:
            raise GitHubAPIStatus(
                "tracker.project_number set but tracker.project_slug is empty; "
                "cannot derive project owner",
                code="github_api_status",
            )
        query = """
        query($owner: String!, $number: Int!, $first: Int!, $after: String) {
          user(login: $owner) {
            projectV2(number: $number) {
              items(first: $first, after: $after) {
                pageInfo { hasNextPage endCursor }
                nodes {
                  id
                  fieldValueByName(name: "Status") {
                    ... on ProjectV2ItemFieldSingleSelectValue { name }
                  }
                  content {
                    __typename
                    ... on Issue {
                      id
                      number
                      title
                      state
                      body
                      url
                      createdAt
                      updatedAt
                      labels(first: 20) { nodes { name } }
                    }
                  }
                }
              }
            }
          }
        }
        """
        issues: list[Issue] = []
        cursor: str | None = None
        status_filter_active = bool(self._active_statuses)
        status_set = set(self._active_statuses)
        while True:
            variables: dict[str, Any] = {
                "owner": self._project_owner,
                "number": self._project_number,
                "first": 100,
            }
            if cursor:
                variables["after"] = cursor
            data = await self._post_graphql(query, variables)
            user_block = data.get("user") or {}
            project = user_block.get("projectV2") if isinstance(user_block, dict) else None
            if not project:
                return issues
            items_block = project.get("items") or {}
            nodes = items_block.get("nodes") or []
            page_info = items_block.get("pageInfo") or {}
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                content = node.get("content")
                normalized = _gql_issue_to_normalized(
                    content if isinstance(content, dict) else None
                )
                if normalized is None:
                    continue
                if normalized.state.lower() not in self._active_states:
                    continue
                if status_filter_active:
                    fv = node.get("fieldValueByName")
                    status_name = fv.get("name") if isinstance(fv, dict) else None
                    if not status_name or status_name.lower() not in status_set:
                        continue
                issues.append(normalized)
            if not page_info.get("hasNextPage"):
                return issues
            cursor = page_info.get("endCursor")
            if not cursor:
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
