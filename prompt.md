# User Prompts Log

This file records every prompt issued by the user (Will) that drives the Symphony Python implementation.

Conventions:
- Each entry begins with `[Will]`
- Entries are appended in chronological order (most recent at the bottom)
- This file is updated and committed at the start of every new task so the assistant always reads it before starting work

---

## Entry 1 — Initial planning request

**[Will]**
read the spec.md, then try implement a python version, make sure every spec is implemented and verified. do it in a way of BDD+TDD. issue tracker should be designed as replacable, so do the runner, let's say github+opencode. check all permission required or maybe required for further operations as the starting point, you may want read the config first. and also there is a Elixir version for reference.

Interpretation / follow-up actions:
- Read `SPEC.md` (the canonical 18-section specification) and the Elixir reference under `elixir/` to confirm architecture parity.
- Design a tracker Protocol that is replaceable, with `GitHubTracker` as the first real adapter.
- Design a runner Protocol that is replaceable, with `OpenCodeRunner` as the first real adapter (over `opencode acp`).
- Use BDD (pytest-bdd) + TDD (pytest unit) methodologies; one test per behavior in SPEC §17.

Outcome: produced `plan.md` v1 with full architecture, conformance map, and work plan. Implementation pending.

---

## Entry 2 — Plan/prompt persistence

**[Will]**
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

**[Will]**
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

## Entry 4 — Pre-flight permission grant before each build

**[Will]**
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
