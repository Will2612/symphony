"""Pytest fixtures for the live e2e tests.

The live tests live under `tests/live/` (per the `make live`
target). They are NOT run by `make all` — only by
`SYMPHONY_RUN_LIVE_E2E=1 make live`.

The fixtures here are intentionally minimal; live tests do the
heavy lifting inline (creating/closing GitHub issues, etc.).
"""
