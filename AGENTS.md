# AGENTS.md

Symphony is a long-running orchestrator that turns issue-tracker work into
isolated agent runs. It ships as **two reference implementations** of one
language-agnostic spec; the spec, not the implementations, is authoritative.

## Authoritative spec

`SPEC.md` (root) is the source of truth. It defines the workflow contract
(`WORKFLOW.md`), the orchestrator state machine, the runner protocol, the
tracker protocol, and §17's test matrix. `SPEC_OVERVIEW.md` is a one-page
table of contents — read it first if the spec feels long.

The implementations may be a **superset** of the spec, but they must not
contradict it. If your change meaningfully alters behavior, update SPEC.md
in the same PR so it stays current.

## Layout

```
SPEC.md                 Authoritative spec (v1, 18 sections + 2 appendices)
SPEC_OVERVIEW.md        1-page TOC for SPEC.md
plan.md                 Python implementation plan (v2, TDD-stepped)
prompt.md               Running log of [Guideline]-marked user prompts
checklist.md            Plan-review findings (closed items, with commit refs)
QandA.md                Resolved + open design questions
elixir/                 Elixir/OTP reference (mature; has CI; tracker: Linear)
  └─ AGENTS.md          Language-specific rules, env, gates, PR conventions
python/                 Python implementation (active TDD/BDD; tracker: GitHub; runner: OpenCode)
  └─ AGENTS.md          Language-specific rules, env, gates, build gate
.codex/                 Repo-local Codex skills (commit, debug, land, linear, pull, push)
.github/workflows/      CI (currently elixir-only)
```

`README.md` (root) is for end users; the per-language `README.md` covers
install and run for that implementation. **Read both before proposing changes.**

## Build gates

- Elixir: `make -C elixir all` (fmt-check + lint + coverage + dialyzer).
  Threshold: 100% coverage on the non-ignored modules (see `mix.exs`).
- Python: `make -C python all` (ruff format + ruff check + mypy --strict +
  pytest + coverage). Threshold: 95% on `src/symphony/`.
- Deploy: `make -C deploy all` (syntax + smoke; see `deploy/README.md §Verifying deploy changes`).

CI (`.github/workflows/make-all.yml`) only runs the Elixir gate. The Python
gate is local-only until the Python implementation is feature-complete.

## Entry points

- Elixir: `elixir/bin/symphony <WORKFLOW.md>`; CLI module
  `SymphonyElixir.CLI` (`mix.exs` → escript). Tracker: Linear (GraphQL).
  Runner: `codex app-server` over stdio.
- Python: `symphony <WORKFLOW.md>` (console script from `pyproject.toml`)
  or `python -m symphony`. Tracker: GitHub REST (httpx). Runner:
  `opencode acp` over stdio. PyPI distribution is `symphony-py` (the bare
  `symphony` name is already taken); importable package is `symphony`.

CLI guardrail: both implementations require an explicit ack flag before
starting (Python: `--i-understand-that-this-will-be-running-without-the-usual-guardrails`;
Elixir: mirrors the same). The orchestrator runs with reduced guardrails
by design — this is the spec posture, not a bug.

## Per-implementation rules

Read the relevant file before touching any code:

- `elixir/AGENTS.md` — env (Elixir 1.19.x / OTP 28 via `mise`), `@spec`
  rules, `mix specs.check` + `mix pr_body.check`, PR template format.
- `python/AGENTS.md` — TDD+BDD discipline, mypy --strict, fakes under
  `tests/_fakes/`, 10 MB line buffer on the runner subprocess, kv-log
  field whitelist, no broad `except Exception`.

## Repo-wide workflow rules (from `prompt.md`)

These are user-issued directives; future agents must honor them:

1. **Read `prompt.md` at the start of every task.** It records user
   instructions marked with the literal prefix `[Guideline]`. Prompts
   without that prefix are **not** recorded — do not invent `[Guideline]`
   markers; only append when the user's message actually starts with
   `[Guideline]`. Check `prompt.startswith("[Guideline]")` before writing.

2. **Plan changes are committed per file.** When `plan.md`, `prompt.md`,
   `checklist.md`, or `QandA.md` changes, that file gets its own commit so
   history is auditable.

3. **Plan-review findings → `checklist.md`.** When reviewing `plan.md`
   against `SPEC.md` or the Elixir reference, surface gaps as a stable-ID
   checklist (`C#` / `M#` / `m#`) with a SPEC reference and a concrete
   next action. Tick items when folded into the plan; reference the
   commit. Do not roll gaps back into `plan.md` until they're addressed.

4. **Open questions → `QandA.md`.** When a design question arises, raise
   it in the "Open" section with context. When resolved, move it to
   "Resolved" with the resolution verbatim (commit ref included). One
   question at a time; resolve in chronological order.

5. **Use the `question` tool for clarifications.** When asking the user
   to choose between discrete options, prefer `question` over free-form
   prose. Free-form prose is reserved for open-ended asks. A `question`
   call may carry multiple questions in one batch.

6. **Live e2e is opt-in.** Real network calls and real subprocess
   integration tests are gated by `SYMPHONY_RUN_LIVE_E2E=1` and must
   be **skipped, not silently passed**, when the env is absent. Both
   Python (`make -C python live`) and Elixir (`make -C elixir e2e`)
   honor this.

7. **PR body format.** Follow `.github/pull_request_template.md`
   exactly. The Elixir CI lints PR descriptions with `mix pr_body.check`;
   use `mix pr_body.check --file <path>` to validate locally.

## Spec-backed non-obvious things

- The orchestrator is a **single-authority** state machine: one async
  task owns `OrchestratorState`, and every mutation goes through an
  `asyncio.Lock` (Python) or a dedicated `Orchestrator` GenServer (Elixir).
  Don't add background writers.

- **Token totals are absolute, not incremental.** Use the runner's
  authoritative `total` field; the `last`/delta is diagnostic only.
  A generic `usage` field is never treated as cumulative. See
  `python/docs/token_accounting.md` (and the Elixir mirror) for the
  six rules.

- **Workspace path containment is checked twice** — once in the
  workspace manager, once in the runner before subprocess spawn.
  Defense in depth; do not collapse them.

- **`api_key` is never logged.** Both implementations use a field
  whitelist at the log layer; forbidden names (`api_key`, `password`,
  `secret`, `token`) are dropped silently. This is enforced centrally,
  not at the call site.

- **10 MB line buffer on the runner subprocess is mandatory** (SPEC §10.1).
  Tested explicitly in `python/tests/unit/test_opencode_runner.py::test_line_buffer_limit`.

- **`hooks.after_create` runs only on new workspace creation**; `after_run`
  and `before_remove` failures are **ignored** (logged at WARN); only
  `before_run` failure aborts the attempt. This is the spec contract —
  don't reverse it.

- **Stall detection disables when `codex.stall_timeout_ms <= 0`** (SPEC §8.5).
  Don't treat 0 as "fire immediately".

- **Reconciliation failure keeps workers running** (SPEC §8.5). When
  `tracker.fetch_issue_states_by_ids` returns an error, the next tick
  retries; do not terminate workers as a side-effect.

- **Restart recovery is filesystem- and tracker-driven, not in-memory.**
  Exact scheduler state is not restored; SPEC §14.3 is explicit that
  a fresh `OrchestratorState` is fine on boot.

## Things to NOT do

- Do not commit secrets, tokens, or `~/.linear_api_key`/`GITHUB_TOKEN`
  values. The `.gitignore` at the root only ignores `.idea/`; per-language
  ignore files cover the rest.
- Do not push directly to `main`. Use the PR template; squash-merge via
  the `land` skill in `.codex/skills/land/`.
- Do not edit the elixir `WORKFLOW.md` or python `examples/*.md` files
  to "test something" without reverting — those are sample contracts
  consumed by users.
- Do not introduce a Linear adapter or an SSH worker pool in Python v1.
  Both are explicitly out of scope (`plan.md` §13); `tracker.assignee`
  is dropped for v1 (`QandA.md` G-Q2). Stub them; don't ship them.
- Do not record user prompts in `prompt.md` that don't start with
  `[Guideline]`. The filter is a literal-prefix check at write time.
