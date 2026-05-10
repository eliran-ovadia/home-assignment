# ADR 015: UUID-Based Anonymous User Sessions

**Date:** 2026-05-10
**Status:** Accepted

## Context

ADR 014 introduced per-user data isolation, which requires the system to know which request belongs to which user. Full authentication (passwords, JWT, login page) is out of scope for this assignment and is explicitly documented as a production gap in `docs/PRODUCTION_ROADMAP.md`. A lighter mechanism is needed.

## Decision

Use UUID-based anonymous sessions:

- The **frontend** generates a UUID v4 on first load and stores it in `localStorage`.
- Every **API request** includes the UUID as the `X-Session-Token` request header.
- The **backend** has a `get_current_user()` FastAPI dependency that looks up the token in the `users` table. If it does not exist, it creates a new `users` row automatically (first-seen = auto-register). The resolved `User` object is injected into every route.
- No passwords, no login page, no JWT — just a stable identity per browser session.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **UUID anonymous session (chosen)** | Zero friction for reviewer. No credentials to manage. Achieves isolation without any auth infrastructure. | No access control — anyone with the UUID can see the data. Acceptable for a demo. |
| Full JWT auth | Production-grade security. Per-user roles. | Login page, password hashing, token refresh, out of scope for the assignment. |
| IP-based identification | No client changes needed. | Unreliable (NAT, proxies). Not suitable for multiple users at the same IP. |
| No user concept (shared state) | Simplest backend. | All users see the same data. Breaks with multiple concurrent users entirely. |

## Consequences

- All API endpoints require the `X-Session-Token` header. A missing or malformed token returns `400 Bad Request`.
- The `get_current_user()` FastAPI dependency (in `src/api/deps.py`) is the single point of user resolution. All routes receive a `User` object — no route directly touches the session token.
- If a user clears `localStorage`, they get a fresh session with empty data. This is expected and acceptable for anonymous mode.
- No access control between sessions: someone who knows another user's UUID can access their data. This is a known gap, documented in `AI_USAGE.md`.

## Production Path

Replace `get_current_user()` with a JWT-based implementation. The function signature stays identical — all route code is unchanged. The `User` object shape (id, session_token, created_at) can be extended with email/role fields without touching the business logic layer.
