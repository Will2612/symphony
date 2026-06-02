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
- Enumerate permissions/capabilities needed before any mutation.

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
