# ADR 004: SQLAlchemy Core with Hand-Written SQL (No ORM)

**Date:** 2026-05-06
**Status:** Accepted

## Context

The role requires SQL knowledge. An ORM abstracts SQL away, which can hide performance characteristics, obscures query complexity, and makes it impossible to demonstrate SQL fluency during a code review. The company's existing system is pure Python without heavy ORM abstractions.

## Decision

Use **SQLAlchemy Core** (not the ORM) to execute hand-written SQL queries. Use **Alembic** for schema migrations, with migration scripts written in raw SQL via `op.execute("...")`.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **SQLAlchemy Core + raw SQL** | Full SQL visibility; demonstrates query-writing skill; matches company culture; fine-grained control over every query | More verbose than ORM; relationships must be managed manually |
| SQLAlchemy ORM | Less boilerplate; relationships handled automatically | Hides SQL; generates suboptimal queries by default; conflicts with the goal of demonstrating SQL knowledge |
| asyncpg / psycopg3 directly | Maximum performance; zero abstraction overhead | No connection pooling; no migration tooling; more infrastructure to build manually |

## Consequences

- Every query is explicitly written in SQL — there are no auto-generated queries
- SQLAlchemy is responsible for: connection pooling, transaction management, and parameterised queries (which prevent SQL injection)
- Alembic migrations are written in raw SQL, keeping migration history readable and auditable
- SQL schema design decisions are visible in `migrations/versions/` and can be discussed in detail
