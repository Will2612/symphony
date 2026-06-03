Feature: GitHub tracker integration
  As an operator
  I want the GitHub tracker to fetch candidate and terminal issues correctly
  So that the orchestrator can dispatch runs against GitHub Issues (SPEC §11, §17.3)

  @unit-test("test_github_tracker.py")
  Scenario: Candidate issues use active states and project slug
    Given a configured GitHub tracker with active states
    When the tracker fetches candidates
    Then the GitHub API is called with state and labels filter
    And only non-terminal issues are returned

  @unit-test("test_github_tracker.py")
  Scenario: Pagination is followed via the Link header
    Given a paginated GitHub response
    When the tracker fetches candidates
    Then subsequent pages are requested until no next link
    And pagination order is preserved

  @unit-test("test_github_tracker.py")
  Scenario: Empty active state list returns no candidates and makes no API call
    Given a GitHub tracker with empty active states
    When the tracker fetches candidates
    Then the tracker returns an empty list
    And no HTTP request is made

  @unit-test("test_github_tracker.py")
  Scenario: Custom tracker.endpoint is honored
    Given a GitHub tracker with a custom endpoint
    When the tracker fetches candidates
    Then all requests go to the custom endpoint

  @unit-test("test_config_validate.py")
  @unit-test("test_tracker_base.py")
  Scenario: tracker.kind memory is accepted
    Given a WORKFLOW.md that declares tracker.kind memory
    When the orchestrator initializes
    Then the orchestrator uses MemoryTracker
    And no HTTP request is made

  @unit-test("test_github_tracker.py")
  Scenario: All 8 GitHub error categories map to typed exceptions
    Given a GitHub API returning 401 or 403 or 404 or 429 or 5xx
    When the tracker fetches candidates
    Then a typed GitHub exception is raised with a stable code
    And the orchestrator logs and continues without dispatching

  @unit-test("test_normalize.py")
  Scenario: Labels are lowercased during normalization
    Given a candidate issue with mixed-case labels
    When the issue is normalized
    Then the labels are lowercased

  @unit-test("test_normalize.py")
  Scenario: Blockers are derived from the inverse blocks relation
    Given an issue A with blocks pointing to B
    When the issues are normalized
    Then B has blocked_by containing A
