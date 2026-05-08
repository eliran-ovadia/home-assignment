# ADR 001: Python 3.12

**Date:** 2026-05-06
**Status:** Accepted

## Context

The Python version must be explicitly pinned. The choice affects language features available, library compatibility, performance, and how long the version receives security patches.

## Decision

Use **Python 3.12**.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Python 3.12** | Supported until Oct 2028; significantly improved error messages; 5–15% faster than 3.11; f-string improvements (PEP 701); well-adopted ecosystem | Not the absolute latest |
| Python 3.13 | Latest features; further perf gains via experimental no-GIL mode | Released Oct 2024 — some libraries are still catching up; higher risk for a time-boxed assignment |
| Python 3.11 | Very stable; wide library support | Missing 3.12 type system improvements; older |

## Consequences

- `requires-python = ">=3.12"` in `pyproject.toml`
- Docker image is `python:3.12-slim`
- The `type` keyword alias (PEP 695) is available
- Improved `traceback` output reduces debugging time
