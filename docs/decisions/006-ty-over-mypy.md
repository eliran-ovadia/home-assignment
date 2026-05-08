# ADR 006: ty over mypy for Static Type Checking

**Date:** 2026-05-06
**Status:** Accepted

## Context

Static type checking is essential for catching bugs before runtime and for making intent explicit in the code. `mypy` has been the Python standard for years, but it is slow, often frustrating to configure, and written in Python (so it cannot take advantage of Rust-level performance).

## Decision

Use **ty** (by Astral, the team behind Ruff and uv).

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **ty** | Rust-based — dramatically faster than mypy; same toolchain vendor as Ruff and uv (consistent config, no cross-tool friction); actively developed | Newer (2025); does not yet cover every mypy edge case; no official pre-commit mirror yet |
| mypy | Industry standard; extensive documentation; broad plugin support | Slow; requires separate stubs packages; Python-based performance ceiling |
| pyright / pylance | Very accurate; backed by Microsoft; fast | Primarily a VS Code / LSP tool; less ergonomic for CLI and CI use |

## Consequences

- Type checking runs as a local pre-commit hook (`ty check src/`) using a `repo: local` hook (since ty does not yet have an official pre-commit mirror)
- Configuration lives in `[tool.ty]` in `pyproject.toml`
- The entire quality toolchain (ruff + ty + uv) is from the Astral ecosystem — one vendor, one config file, consistent philosophy
- If a specific edge case requires mypy, it can be run ad-hoc; the two tools are not mutually exclusive
