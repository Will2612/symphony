# Symphony Swift

A Swift 6 daemon that implements the [Symphony service specification](SPEC.md).
Symphony is a long-running supervisor that watches an issue tracker, dispatches
each ticket to an isolated workspace, runs a coding agent, and reports the
result back to the board.

This repository is the Swift port. It replaces the upstream reference's
hard-coded Linear tracker with **GitHub Projects v2** and treats coding agents
as a replaceable worker protocol (opencode/ACP by default, codex v2 JSON-RPC as
an option). M0 ships only the runtime shell: a CLI that prints its version,
a multi-architecture Docker image, and a CI pipeline that publishes the image
to GHCR. Business logic lands in M1–M4.

## Quick start

```bash
docker run --rm ghcr.io/will2612/symphony:dev --version
```

Expected output: `symphony 0.0.0-dev (swift 6.3.2)`.

## Further reading

- [`Plan.md`](Plan.md) — implementation plan, milestones M0–M4, and the
  per-file scope for the M0 runtime shell.
- [`SPEC.md`](SPEC.md) — language-agnostic service specification (the
  normative source of truth).
- [Symphony teaching workspace](https://github.com/Will2612/symphony) —
  42-lesson curriculum that walks through the SPEC section by section and
  points back to specific files in this repository for verification.

## License

This project is licensed under the [Apache License 2.0](LICENSE).
