# AGENTS.md

Local rules for any agent (human or AI) working in this directory. Mirrors the spirit of `elixir/AGENTS.md`.

## Build gate

Every change must end with `make all` green:

```bash
make format && make lint && make type && make test
```

- `make type` runs `mypy --strict src/symphony`.
- `make test` runs `tests/unit` and `tests/features` (BDD).
- Coverage threshold is 95% on `src/symphony/`.
- Live e2e is opt-in: `SYMPHONY_RUN_LIVE_E2E=1 make live`.

## TDD discipline

- One failing test per behavior in SPEC §17. The test is written first, then the production code.
- A step is "done" only when `make all` is green. No step moves to the next without green.
- Fakes live in `tests/_fakes/`. `conftest.py` imports them and exposes them as pytest fixtures. Production code MUST NOT import from `tests/`.

## Code style

- Python 3.12+ syntax.
- Type hints everywhere; `mypy --strict` is non-negotiable.
- All async code uses `asyncio`.
- No broad `except Exception`. The base class is `symphony.errors.SymphonyError`; catch only declared subtypes at each layer.
- All logging uses the kv logger from `symphony.observability.log`. The `api_key` field is never logged.

## Documentation

- `docs/CONFORMANCE.md` is the spec → test pointer map. Update it whenever a new behavior is tested.
- `docs/logging.md` documents the structured-log format.
- `docs/token_accounting.md` documents the token-total rules (mirrors SPEC §13.5).

## Subprocess safety

- Spawning `opencode acp` requires `bash -lc <cmd>` with `cwd=workspace` and PATH inherited (SPEC §10).
- A 10 MB line buffer is mandatory.
- The subprocess's stdout/stdin are newline-delimited JSON-RPC.

## Permissions

The orchestrator runs with reduced guardrails by design. The CLI requires `--i-understand-that-this-will-be-running-without-the-usual-guardrails` before starting. This is mirrored from the Elixir reference.
