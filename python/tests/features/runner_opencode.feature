Feature: OpenCode runner lifecycle
  As an operator
  I want the runner to drive opencode acp correctly so that issues get
  Implemented in isolated workspaces (SPEC §10, §17.5)

  @unit-test("test_opencode_runner.py")
  Scenario: Subprocess launched via bash with workspace cwd
    Given a session to start
    When the runner starts
    Then bash -lc opencode is spawned with cwd workspace
    And PATH is inherited

  @unit-test("test_opencode_runner.py")
  Scenario: Startup handshake completes before any prompt
    Given a runner subprocess
    When the runner starts
    Then it waits for session_started
    And the runner refuses to send prompts before the handshake

  @unit-test("test_opencode_runner.py")
  Scenario: First turn title contains the issue identifier and title
    Given an issue identifier and title
    When the first prompt is sent
    Then the title includes the identifier and title text

  @unit-test("test_opencode_runner.py")
  Scenario: Read timeout is enforced
    Given a runner with no response within read_timeout_ms
    When the runner waits
    Then ResponseTimeout is raised

  @unit-test("test_opencode_runner.py")
  Scenario: Turn timeout is enforced
    Given a turn that does not complete within turn_timeout_ms
    When the runner waits
    Then TurnTimeout is raised

  @unit-test("test_opencode_runner.py")
  Scenario: 10 MB line buffer is enforced
    Given a JSON-RPC line exceeding 10 MB
    When the runner reads it
    Then the line is rejected or truncated

  @unit-test("test_opencode_runner.py")
  Scenario: Approval policy auto-approve is in effect
    Given the default approval policy
    When the runner receives an approval request
    Then it auto-approves

  @unit-test("test_opencode_runner.py")
  Scenario: Unsupported tool call is a failure not a stall
    Given the runner emitting an unsupported tool call
    When the orchestrator processes the event
    Then the attempt is marked FAILED

  @unit-test("test_opencode_runner.py")
  Scenario: User input required is a hard failure
    Given the runner emitting TURN_INPUT_REQUIRED
    When the orchestrator processes the event
    Then the attempt is marked FAILED with code user_input_required

  @unit-test("test_opencode_runner.py")
  @unit-test("test_orchestrator_service.py")
  Scenario: Token and rate-limit extraction
    Given the runner reports token usage and rate limits
    When the orchestrator processes the update
    Then last_token_usage is recorded
    And the rate-limit snapshot is updated

  @unit-test("test_opencode_runner.py")
  Scenario: All 9 runner error categories are mapped
    Given any of the 9 SPEC 10.6 error categories
    When the runner hits the error
    Then a typed RunnerError subclass is raised with a stable code
