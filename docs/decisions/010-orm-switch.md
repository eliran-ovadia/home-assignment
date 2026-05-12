# ADR 010: SQLAlchemy ORM (supersedes ADR 004)

**Date:** 2026-05-09
**Status:** Accepted — supersedes ADR 004

## Context

ADR 004 chose SQLAlchemy Core with hand-written SQL to maximise explicitness and demonstrate SQL knowledge. The assignment specification states that ORM usage is "preferred". After reviewing the repository layer, the added boilerplate of Core (manual `Table()` definitions, manual column mapping in every query, manual result-to-dict conversion) slows development without providing meaningful benefit at this project's scale.

## Decision

Use SQLAlchemy 2.0 ORM with the modern `Mapped[]` / `mapped_column` declarative style. All database access goes through an `AsyncSession` (asyncpg driver). `db/models.py` defines the mapped classes. Repositories use the SQLAlchemy 2.0 idiom: `session.execute(select(...))` for reads, `session.add()` for single inserts, and `session.execute(insert(Model).values(...))` over a list for bulk inserts.

SQLAlchemy is still responsible for connection pooling, transaction management, and parameterised queries (preventing SQL injection). The ORM layer is added on top.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **SQLAlchemy ORM** | Less boilerplate, preferred by assignment, models serve as documentation | Slightly more "magic" — generated SQL less visible |
| SQLAlchemy Core (original ADR 004) | Fully explicit SQL, complete control | Significant boilerplate in repositories, manual column mapping everywhere |
| Raw psycopg2 | Maximum control, zero abstraction | No connection pooling, no parameterisation helpers, no migration support |

## Consequences

- `db/schema.py` is replaced by `db/models.py` containing ORM-mapped classes.
- Repositories are significantly simpler — no manual column extraction from `Row` objects.
- Alembic migrations continue to work unchanged (Alembic reads the ORM models via `Base.metadata`).
- Bulk inserts use `session.execute(insert(Model), list_of_dicts)` — the SQLAlchemy 2.0 replacement for `bulk_insert_mappings()`, with the same `executemany`-driven performance characteristics.
- The ADR 004 rationale (explicit SQL, no magic) is still valid for production systems with complex query requirements; for this project's scope, ORM is the right trade-off.
