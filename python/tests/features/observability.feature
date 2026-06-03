Feature: Observability logging snapshot and HTTP surface
  As an operator
  I want logs and a snapshot endpoint so I can see what Symphony is doing
  (SPEC §13, §17.6, §17.7)

  @unit-test("test_observability_log.py")
  Scenario: Structured logging with whitelisted context
    Given the orchestrator logging
    When a log line is emitted
    Then the line is structured as ts level logger msg k v
    And the whitelisted context fields are included
    And the api_key field is never logged

  @unit-test("test_observability_log.py")
  Scenario: Sink failure does not crash the orchestrator
    Given a log sink that fails to write
    When the sink handler runs
    Then a single WARNING line is written
    And the orchestrator continues

  @unit-test("test_observability_server.py")
  Scenario: Snapshot API exposes the full per-issue field set
    Given the HTTP server running
    When GET api issue is called
    Then the response includes the full field set

  @unit-test("test_observability_server.py")
  Scenario: Snapshot timeout or unavailable returns 503 or 404
    Given the service is not yet ready
    When the snapshot endpoint is called
    Then the service returns 503 or 404

  @unit-test("test_orchestrator_service.py")
  Scenario: Token aggregation across updates
    Given the runner emitting multiple token updates
    When the orchestrator aggregates
    Then the running total uses absolute deltas

  @unit-test("test_orchestrator_service.py")
  Scenario: Operator-visible validation failures on startup
    Given a WORKFLOW.md that fails preflight
    When the orchestrator starts
    Then an ERROR is logged
    And the CLI exits with code 1

  @unit-test("test_observability_server.py")
  Scenario: HTTP error envelope for 404 or 405 or 500
    Given the HTTP server returning an error
    When the response is inspected
    Then the body is a structured error envelope
