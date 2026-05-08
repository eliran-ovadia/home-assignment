# ADR 003: Ruff as the Unified Linting and Formatting Toolchain

**Date:** 2026-05-06
**Status:** Accepted

## Context

Python projects traditionally require multiple tools for code quality: `flake8` for linting, `black` for formatting, `isort` for import ordering, and `pyupgrade` for modernisation. Managing these separately leads to configuration drift, version conflicts, and slow CI runs.

## Decision

Use **Ruff** as the single tool for linting, formatting, and import sorting. Keep **mypy** separately for static type checking, as Ruff does not perform type inference.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Ruff** | 10–100× faster than alternatives; replaces flake8 + black + isort in one binary; single `[tool.ruff]` section in `pyproject.toml`; actively maintained by Astral | Younger project (2022); some niche flake8 plugins not yet ported |
| flake8 + black + isort | Mature; widely documented | Three separate tools to pin and configure; potential ordering conflicts; noticeably slower |
| pylint | Very thorough analysis | Extremely slow; verbose output; configuration overhead outweighs gains for an assignment scope |

## Consequences

- `ruff check` (lint) and `ruff format` (format) are the only style commands needed
- Pre-commit hook runs both before every commit, so the git history is clean by construction
- CI fails on any Ruff violation or format difference
- `mypy --strict` runs separately to enforce type correctness
