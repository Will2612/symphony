Feature: Orchestrator dispatch and reconciliation
  As an operator
  I want the orchestrator to dispatch the right issues and recover from failures
  So that the workload keeps moving without manual intervention (SPEC §7, §8, §17.4)

  @unit-test("test_orchestrator_dispatch.py")
  Scenario: Dispatch order is priority, created_at, identifier
    Given multiple eligible candidates
    When the orchestrator dispatches
    Then issues are ordered by priority then created_at then identifier

  @unit-test("test_orchestrator_dispatch.py")
  Scenario: A Todo issue with non-terminal blockers is not dispatched
    Given a Todo issue blocked by a non-terminal issue
    When the orchestrator dispatches
    Then the Todo issue is not dispatched

  @unit-test("test_orchestrator_reconcile.py")
  Scenario: Active-state refresh updates running snapshot
    Given a running issue and an active tracker
    When reconciliation runs
    Then the running session is updated

  @unit-test("test_orchestrator_reconcile.py")
  Scenario: Non-active state stops the worker without cleanup
    Given a running issue transitioning to a non-active state
    When reconciliation runs
    Then the worker is terminated
    And the workspace is not removed

  @unit-test("test_orchestrator_reconcile.py")
  Scenario: Terminal state stops and cleans the workspace
    Given a running issue transitioning to a terminal state
    When reconciliation runs
    Then the worker is terminated
    And the workspace is removed

  @unit-test("test_orchestrator_reconcile.py")
  Scenario: Reconciliation failure keeps workers running
    Given the tracker returning an error on state refresh
    When reconciliation runs
    Then workers for affected issues are not terminated

  @unit-test("test_orchestrator_reconcile.py")
  Scenario: Stall detection kills and retries stalled runs
    Given a session streaming beyond stall_timeout_ms
    When reconciliation runs
    Then the worker is killed
    And a retry entry is scheduled with exponential backoff

  @unit-test("test_orchestrator_reconcile.py")
  Scenario: Stall detection is disabled when stall_timeout_ms is 0
    Given a session and codex.stall_timeout_ms = 0
    When reconciliation runs
    Then no worker is killed for being stalled

  @unit-test("test_orchestrator_service.py")
  Scenario: Restart-recovery re-dispatches eligible issues
    Given a fresh orchestrator start
    When the first tick runs
    Then OrchestratorState is initialized empty
    And eligible candidates are re-dispatched

  @unit-test("test_orchestrator_service.py")
  Scenario: Per-tick defensive reload
    Given a running orchestrator
    When a tick runs without watchfile events
    Then WORKFLOW.md is re-validated anyway

  @unit-test("test_orchestrator_service.py")
  Scenario: Startup terminal workspace cleanup runs once at boot
    Given a fresh orchestrator start
    When startup runs
    Then terminal workspaces are removed
