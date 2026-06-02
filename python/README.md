# symphony-py

Python implementation of the Symphony service per [`SPEC.md`](../SPEC.md).

Symphony is a per-issue orchestrator that drives an agent runner (OpenCode, over `opencode acp`) against a replaceable issue tracker (GitHub first; Linear as a future adapter). The runtime reads a `WORKFLOW.md` policy file, polls the tracker for candidate issues, and runs a fresh agent session per issue inside an isolated workspace.

## Status

v0.1.0 — Alpha. Implements the protocol surface and conformance gate defined in `SPEC.md`. Pre-1.0; the public API is not yet stable.

## Install

```bash
# Runtime deps only
make install

# Development install (editable, with dev tooling)
make editable
```

This installs the `symphony` CLI command (entry point from `pyproject.toml`).

## Run

```bash
# Requires a WORKFLOW.md in the current directory
symphony --i-understand-that-this-will-be-running-without-the-usual-guardrails

# Custom path
symphony /path/to/WORKFLOW.md --i-understand-that-this-will-be-running-without-the-usual-guardrails

# With the observability HTTP server
symphony --port 7842 --i-understand-that-this-will-be-running-without-the-usual-guardrails
```

## Develop

```bash
# The conformance gate
make all                  # format + lint + type + test + coverage

# Individual steps
make format               # ruff format
make lint                 # ruff check
make type                 # mypy --strict
make test                 # pytest (unit + BDD features)
make coverage             # pytest with coverage report
make live                 # live e2e (requires SYMPHONY_RUN_LIVE_E2E=1 + creds)
```

## Layout

See [`../plan.md`](../plan.md) for the design plan and [`../checklist.md`](../checklist.md) for the open plan-review findings.

```
src/symphony/             Production code
tests/unit/               TDD: one test per behavior in SPEC §17
tests/features/           BDD: Gherkin scenarios
tests/steps/              pytest-bdd step definitions
tests/live/               opt-in live e2e (env-gated)
tests/_fakes/             test doubles used by conftest.py
docs/                     CONFORMANCE.md, logging.md, token_accounting.md
examples/                 sample WORKFLOW.md files
```

## License

Apache-2.0
