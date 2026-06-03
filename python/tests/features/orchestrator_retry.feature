Feature: Orchestrator retry queue and backoff
  As an operator
  I want retries to be scheduled correctly so transient failures recover
  And persistent failures do not burn CPU (SPEC §7.4, §8.3, §17.4)

  @unit-test("test_orchestrator_retry.py")
  Scenario: Normal exit is followed by a 1s continuation retry
    Given a worker that exits normally
    When the orchestrator processes the result
    Then a RetryEntry is scheduled with delay_ms 1000
    And the issue is re-dispatched on the same live session

  @unit-test("test_orchestrator_retry.py")
  Scenario: Abnormal exit triggers exponential backoff
    Given a worker that exits abnormally
    When the orchestrator processes the result
    Then a RetryEntry is scheduled with exponential backoff

  @unit-test("test_orchestrator_retry.py")
  Scenario: Backoff is capped at agent.max_retry_backoff_ms
    Given a worker that has failed many times
    When the orchestrator computes the backoff
    Then delay_ms equals agent.max_retry_backoff_ms

  @unit-test("test_orchestrator_retry.py")
  Scenario: RetryEntry has the expected shape
    Given a retry that is scheduled
    When the entry is inspected
    Then it has fields id, attempt, due, error

  @unit-test("test_orchestrator_retry.py")
  Scenario: Slot exhaustion requeues with an error
    Given all concurrent agent slots are taken
    When the orchestrator dispatches
    Then the issue is requeued with an error
