# Token Accounting

This document explains how the OpenCode runner reports token usage through
the Agent Client Protocol (ACP) and how Symphony should account for it.

It mirrors `elixir/docs/token_accounting.md` and is tailored to the
Python implementation that drives the `opencode acp` runner. The
upstream Elixir reference is the canonical design contract; this
document pins down the Python-specific details.

## Short Version

- `last_token_usage` means "the latest increment".
- `total_token_usage` means "the cumulative total so far".
- The runner's `tokenUsage` payload carries a `total` field that is
  authoritative.
- Generic `usage` fields are event-specific. Do not assume every
  `usage` payload is a cumulative thread total.

## Primary Source Semantics

The OpenCode `tokenUsage` payload (delivered via ACP) is shaped
approximately like:

```typescript
{
  total: { input: number, output: number, cached_input?: number },
  last:  { input: number, output: number, cached_input?: number },
  model_context_window?: number,
}
```

The implementation in `symphony.runner.opencode._classify_event_usage`
normalizes this to a typed dict with absolute totals extracted from
`total` and per-update deltas extracted from `last`.

## Rules

1. **`last_token_usage` from a runner update is ignored as a cumulative
   number.** It is only used for diagnostics (e.g. log line
   "delta = +1234 input / +567 output"). The running total never
   uses it.

2. **The authoritative total is the absolute `total_tokens` field on
   the runner's `tokenUsage` payload** (i.e. `total.input + total.output`
   on the OpenCode event, or the explicit `total.total_tokens` when
   the runner provides one). When the runner provides only
   `total.input` and `total.output`, Symphony derives
   `total = input + output`.

3. **For each update, compute `delta = absolute_total - last_reported_total_tokens`**
   and add to the run-attempt's running total. If `last_reported_total_tokens`
   is `None` (first update), treat the first update's absolute as
   the running total (no delta).

4. **The orchestrator tracks `last_reported_total_tokens` per
   `LiveSession`** and updates it on every accepted update. The
   value is reset on a fresh session (restart-recovery).

5. **A generic `usage` field (no absolute total) is never treated as
   cumulative.** If the runner only emits a `usage` field, the
   orchestrator logs `runner_token_accounting_unresolved` at WARN
   and the run-attempt's token total stays at its previous value.

6. **Rate-limit data** (`rate_limit.remaining`, `rate_limit.reset_at`)
   is recorded in the snapshot but is NOT part of the run-attempt
   total. It is exposed separately on the observability HTTP
   snapshot.

## Implementation Map

- `symphony.observability.snapshot.extract_token_counts(event)` —
  normalizes the runner's payload into a typed dict
  (`{input, output, total}`). Negative values are clamped to zero
  BEFORE computing `total`. If no `total_tokens` is present but
  `input_tokens + output_tokens` are, the total is derived.
- `symphony.observability.snapshot.aggregate_token_usage(state)` —
  per `LiveSession.usage`, sums `input`, `output`, and `total`
  across all live sessions. If any session reports a `total_tokens`
  value, the aggregate `total_tokens` is the sum of those. If no
  session reports `total_tokens`, the aggregate `total_tokens` is
  derived from `sum(input_tokens) + sum(output_tokens)`.
- `symphony.orchestrator.service` — the orchestrator applies the
  per-update delta rule when consuming a `RunnerEvent` of kind
  `TURN_COMPLETED` (or any event that carries usage).

## Why Absolute Totals Are The Durable Choice

The OpenCode runner, like Codex, consistently prefers cumulative
totals when it needs durable state. If we misclassify a per-turn
`usage` payload as an absolute thread total, later turns can
appear to stall because a smaller per-turn number is compared
against a larger cumulative baseline.

## Recommended Documentation Contract

- Live token totals come from the runner's `tokenUsage.total`
  payload (or `input_tokens + output_tokens` when explicit total
  is missing).
- Incremental `last` deltas are diagnostic only.
- Generic `usage` payloads are event-specific and never assumed
  to be a fresh additive increment.
- Reporting is session-based; multiple turns can occur on one
  session.

## Implementation Checklist

- Prefer `tokenUsage.total` over `tokenUsage.last`.
- Derive `total = input + output` when `total_tokens` is missing
  (and clamp negatives BEFORE summing).
- Track per-session `last_reported_total_tokens` and use it for
  delta computation.
- Do not classify a `usage` payload by field name alone — check
  the event source.
- Do not double-count turn-completed `usage` on top of
  already-counted live updates.
- Rate-limit data is OUT of scope for the per-attempt total.
