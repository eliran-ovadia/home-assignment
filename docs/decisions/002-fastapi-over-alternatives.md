# ADR 002: FastAPI as the HTTP Framework

**Date:** 2026-05-06
**Status:** Accepted

## Context

The role explicitly lists FastAPI as an advantage. The assignment will likely require building an HTTP API. The framework choice affects developer experience, documentation quality, validation, and async support.

## Decision

Use **FastAPI**.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **FastAPI** | Auto-generates OpenAPI docs at `/docs`; native async; Pydantic validation on all inputs/outputs; explicitly mentioned in the role requirements | Smaller community than Flask |
| Flask | Largest Python web community; very mature; flexible | No native async; no auto-docs; validation requires a separate library (marshmallow, etc.) |
| Django REST Framework | Admin panel; auth batteries included | Heavy for a focused API project; ORM-first design conflicts with the pure SQL approach |
| Litestar | Modern, type-safe, comparable to FastAPI | Less documentation; smaller ecosystem; adds unfamiliar risk |

## Consequences

- OpenAPI docs are available at `/api/docs` and `/api/redoc` with zero extra configuration (the `/api` prefix keeps them out of the way of the React static bundle mounted at `/`)
- All request/response shapes are Pydantic models — validation and serialisation are automatic
- Async endpoints are first-class, enabling concurrent DB queries and external HTTP calls
- `uvicorn` is used as the ASGI server
