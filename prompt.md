# User Prompts Log

This file records **only** user prompts that begin with the literal
marker `[Guideline]`. All other prompts are not recorded.

Conventions:
- Each entry begins with `[Guideline]`.
- Entries are appended in chronological order (most recent at the bottom).
- The marker is a literal prefix: any prompt that does **not** start
  with `[Guideline]` is filtered out at write time. This is the single
  authoritative rule; no exceptions.
- This file is updated and committed at the start of every new task
  that contains a recorded prompt, so the assistant always reads it
  before starting work.
- Historical entries that predate this rule keep their original
  prompts verbatim but the marker label is renamed `[Will]` →
  `[Guideline]` for consistency with the new convention.

---

## Entry 1 — Initial planning request

**[Guideline]**
read the spec.md, then try implement a python version, make sure every spec is implemented and verified. do it in a way of BDD+TDD. issue tracker should be designed as replacable, so do the runner, let's say github+opencode. check all permission required or maybe required for further operations as the starting point, you may want read the config first. and also there is a Elixir version for reference.

Interpretation / follow-up actions:
- Read `SPEC.md` (the canonical 18-section specification) and the Elixir reference under `elixir/` to confirm architecture parity.
- Design a tracker Protocol that is replaceable, with `GitHubTracker` as the first real adapter.
- Design a runner Protocol that is replaceable, with `OpenCodeRunner` as the first real adapter (over `opencode acp`).
- Use BDD (pytest-bdd) + TDD (pytest unit) methodologies; one test per behavior in SPEC §17.

Outcome: produced `plan.md` v1 with full architecture, conformance map, and work plan. Implementation pending.

---

## Entry 2 — Plan/prompt persistence

**[Guideline]**
1. put this plan into a plan.md file for future reference, and make a commit. we may adjust the plan later on, everytime we make a change to the plan, make a commit for it.
2. write another file prompt.md to record the prompt from me, identify this by starting with [Will], everytime you see it you update to prompt.md, make a commit for it, then read it on every task.

Interpretation / follow-up actions:
- Create `plan.md` (this is the file) with the full plan content for future reference.
- Create `prompt.md` (this file) to record every `[Will]` prompt.
- Every change to either file MUST be committed separately so history is auditable.
- Before starting any task, the assistant MUST read this file to know the running list of user instructions.

Outcome: created `plan.md` and `prompt.md`; this is the first commit of the pair.

---

## Entry 3 — Plan review, checklist, and Q&A workflow

**[Guideline]**
we will check the plan constantly like this, once there is any findings on the plan, make a checklist.md and make a commit for it. and if there is anything we need to clearify, make a question list and we will check them one by one, once it's done, record it in a QandA.md and make a commit for it.

Interpretation / follow-up actions:
- Establish a recurring plan-review workflow. After every plan change, look for:
  1. **Findings / gaps** → write to `checklist.md` as an actionable checklist (with checkboxes), grouped by priority, each with a SPEC reference and a concrete next action. Commit it.
  2. **Open questions** → propose resolution one at a time. When a question is resolved, record the question + answer in `QandA.md` (living document). Commit it.
- This directive supersedes Entry 2's general "commit plan changes" rule for plan gaps specifically — gaps go to `checklist.md`, not back into `plan.md` until they're addressed.
- `checklist.md` and `QandA.md` are siblings of `plan.md`/`prompt.md` and get the same per-file commit treatment.
- The current plan review (after the v1 plan was committed) produced 10 critical findings (C1–C10), 14 medium findings (M1–M14), and 3 open questions (G-Q1, G-Q2, M12-from-prior-list) — see `checklist.md` and `QandA.md`.

Outcome: created `checklist.md` and `QandA.md`; first commits of each. Future plan reviews add to these files and commit.

---

## Entry 4 — Pre-flight permission grant before each build **(ignore — superseded by Entry 5)**

**[Guideline]**
before each build operation, ask me for full read and write access to this repo with question tool to avoid execution interupt per permission requirement.

Interpretation / follow-up actions:
- Before starting any new build/installation step (pip install, mkdir, file creation, make, pytest, ruff, mypy, git commit, etc.), the assistant MUST pause and ask Will for full read+write access scoped to the current build.
- The request MUST go through the `question` tool (not free-form text), with options that include a clear grant path and a clear deny path. The options should reflect the actual operations the assistant intends to perform in this step.
- "Full read and write" means broad permission for that step — Will will pre-approve the relevant operations so the assistant can execute the entire step without per-command permission interruptions.
- The assistant lists the exact operations it intends to perform in the question description, so Will can decide whether to grant.
- After the step completes, the grant is implicitly revoked; the next step starts with another question-tool request.
- This is in addition to (not a replacement for) the Entry 2 commit-per-file rule and the Entry 3 plan-review workflow.

Outcome: applied to all future build steps starting with TDD Step 1. The first such request will be via the `question` tool.

---

## Entry 5 — Auto-proceed through plan §11 steps

**[Guideline]**
mark prompt entry 4 with (ignore), then proceed following steps unless any interupt.

Interpretation / follow-up actions:
- Entry 4 is now superseded and should be marked `(ignore)` in the heading; its content remains for the historical record but is no longer authoritative.
- Continue executing plan §11 (steps 3-25) sequentially without pausing to ask for permission per step.
- The execution policy is "proceed unless interrupted":
  - "Proceed" = follow the plan, TDD per step, end each step with `make all` green, commit per the Entry 2 rule.
  - "Interrupt" = Will says stop, an unexpected build failure that needs a design decision, an ambiguity in the spec, a plan gap that surfaces mid-implementation, or any out-of-scope request.
- New `[Will]` prompts and plan-review findings still go through the Entry 3 workflow (checklist.md / QandA.md + commits).
- Per-file commits still apply (Entry 2). Multi-file changes within a single step get separate commits where it makes sense, but a tight cluster of related changes (e.g. errors.py + its test) is one commit.
- Coverage gate (95%) and `make all` green gate still apply at the end of every step. A step is "done" only when both pass.

Outcome: keep building. Stop only on interrupt.

---

## Entry 7 — Restrict prompt log to `[Guideline]` markers

**[Guideline]**
the earlier prompts recorded in prompt.md are triggered by [Will] mark, I want to updae it with [Guideline], not every prompt shoudl be recorded, only those starting with [Guideline], any suggestion ?

Interpretation / follow-up actions:
- Rename the existing marker from `[Will]` to `[Guideline]` for every surviving entry (1-5). Entry 6 was already removed manually prior to this change.
- Going forward, only prompts whose first token is the literal `[Guideline]` are appended to this file. All other prompts (questions, status checks, debug conversations, etc.) are filtered out.
- The filter is applied at write time: at the top of every turn, the assistant checks `prompt.startswith("[Guideline]")` before any logging work.
- Historical entries keep their original prompt text verbatim — only the in-line marker label is renamed.
- The rule is documented in this file's header AND in `python/AGENTS.md` so it survives context resets.

Outcome: rule updated. Future prompts without the `[Guideline]` prefix are not recorded.

---

## Entry 8 — Prefer the `question` tool for clarifying questions

**[Guideline]**
提问时优先使用question工具

Interpretation / follow-up actions:
- When the assistant needs to ask the user to choose between discrete options, clarify a parameter, or confirm a setting, prefer the `question` tool over free-form text questions.
- Reserve free-form prose questions for open-ended / qualitative asks where there is no enumerable option set.
- A single `question` tool call may carry multiple related questions (the tool supports a list).
- Each question's `options` list should be 2-4 short, mutually exclusive, mutually exhaustive choices; mark the recommended one first; `description` explains tradeoffs.
- The `custom` input is auto-enabled — users can also type their own answer if no option fits.
- This guideline does not override the Entry 2 prompt.md logging rule: even when a `question` call is in play, the user is not assumed to have issued a `[Guideline]` unless the message starts with that literal marker.

Outcome: future clarifying questions go through the `question` tool by default.
