Feature: WORKFLOW.md loading and CLI surface
  As an operator
  I want the CLI to load WORKFLOW.md and route the orchestrator correctly
  So that I can start Symphony against any path (SPEC §17.7)

  Background:
    Given a valid WORKFLOW.md with tracker.kind memory

  @unit-test("test_cli.py")
  Scenario: Default WORKFLOW.md path is used when no path is given
    Given a valid WORKFLOW.md file exists at the default path
    When I run the CLI with no positional argument
    Then the CLI evaluates the default path
    And the CLI returns exit code 0 if the file exists

  @unit-test("test_cli.py")
  Scenario: Explicit path overrides the default
    Given a valid WORKFLOW.md file at a custom path
    When I run the CLI with the custom path
    Then the CLI uses the explicit path verbatim
    And the CLI returns exit code 1 when the file does not exist

  @unit-test("test_cli.py")
  @unit-test("test_observability_server.py")
  Scenario: --port 0 binds an ephemeral port and clean shutdown returns 0
    Given a valid WORKFLOW.md and the --port 0 flag
    When the observability server starts
    Then the server picks a free port
    And the bound port is written to ObservabilityServer.bound_port
    And a clean shutdown returns 0

  @unit-test("test_cli.py")
  Scenario: Startup failure returns exit code 1
    Given a missing or unparseable WORKFLOW.md
    When the CLI is invoked
    Then the CLI returns 1 with a stderr message

  @unit-test("test_cli.py")
  Scenario: Guardrails banner is shown when the ack flag is missing
    Given a valid WORKFLOW.md
    When the CLI is invoked without the ack flag
    Then a red banner is printed to stderr
    And the CLI returns 1
