# Dispatch for Forensic Auditor 1

## Identity
- Role: Forensic Integrity Auditor 1
- Working Directory: /home/will/Projects/symphony/.agents/teamwork_preview_auditor_1

## Context & Inputs
- Original Request: `/home/will/Projects/symphony/.agents/ORIGINAL_REQUEST.md`
- Target Directory: `/home/will/Projects/symphony/docs/`

## Instructions
1. Perform forensic integrity audit on all generated documentation files in `/home/will/Projects/symphony/docs/`.
2. Check for:
   - Hardcoded fake outputs, dummy/facade claims, or fabricated technical details.
   - Genuine matching between documented structures (OTP supervision tree, Ecto config schema, Linear GraphQL queries, Orchestrator poll loop, Workspace hooks, Codex protocol JSON-RPC methods, LiveView/REST routes) and the actual source code in `elixir/lib/`.
   - Validity of Mermaid diagram syntax and structures.
3. Write your report to `/home/will/Projects/symphony/.agents/teamwork_preview_auditor_1/analysis.md` and handoff report with verdict `CLEAN` or `INTEGRITY VIOLATION` to `/home/will/Projects/symphony/.agents/teamwork_preview_auditor_1/handoff.md`.
4. Notify orchestrator via `send_message`.

## 2026-07-31T21:36:18Z
Perform forensic integrity audit on all documentation files in `/home/will/Projects/symphony/docs/`.
Check for authenticity, accuracy against source code, and valid Mermaid diagram syntax.
Write handoff report with verdict `CLEAN` or `INTEGRITY VIOLATION` to `/home/will/Projects/symphony/.agents/teamwork_preview_auditor_1/handoff.md`.
Send a message to orchestrator when finished.
