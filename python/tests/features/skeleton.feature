Feature: Symphony is installed and discoverable
  As an operator
  I want the symphony package to be importable
  So that the CLI and library work

  @unit-test("test_skeleton.py")
  Scenario: The package exposes a version string
    When I import the symphony package
    Then the version string is non-empty
