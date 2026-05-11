# ADR 016: Corporate Email as Identity, Shared Upload Pool

**Date:** 2026-05-11
**Status:** Accepted
**Supersedes:** ADR 015 (UUID anonymous sessions)

## Context

ADR 014 introduced per-upload result storage. ADR 015 layered UUID-in-`localStorage` "anonymous sessions" on top of it to isolate data per browser session. Two real problems with that combination surfaced during PR 2 implementation:

1. **Cross-device continuity.** A UUID generated on one machine doesn't follow the user to another machine; opening the app on a second device produces a "new user" with no history. For an internal tool where the same person uses a desktop and a laptop, this is a meaningful gap.
2. **The isolation use-case itself was wrong.** The target deployment context is a single organization's intranet, where traders *want* to see each other's uploads. Per-browser isolation was over-engineering for a problem we don't have.

Removing the isolation simplifies several layers (no `user_id` FK chain, no `is_active` flag, no per-user advisory lock, no ownership checks on `set_active`). But we still need a way to remember each user's last-viewed upload across devices. That requires identity.

Full authentication (passwords, JWT, login page) remains out of scope for this assignment and is documented as a production gap in `docs/PRODUCTION_ROADMAP.md` §1.

## Decision

**Identify the user by their corporate email; share all upload data.**

- The **frontend** captures the user's corporate email once via a small landing form, stores it in `localStorage`, and sends it on every request as the `X-Session-Token` header.
- The **backend** treats the header value as an opaque string at the storage layer and validates it as `pydantic.EmailStr` at the API boundary.
- The `users` table has `(id, email UNIQUE, last_viewed_upload_id NULL FK→uploads, created_at)`. No password column, no token column.
- The **`uploads` table** has no `user_id` and no `is_active` — every upload is visible to every user. "Which upload am I looking at" is a per-user preference held in `users.last_viewed_upload_id`.
- The `get_current_user()` FastAPI dependency reads the header, validates the email, and returns the matching `User` row (creating one on first sight). All routes receive a `User` object — no route touches the header directly.

The deployment context that makes this safe is documented as a first-class section in `docs/SPEC.md` §0, summarized as: **the trust boundary is the corporate network perimeter plus the IdP-verified email provisioning chain — not per-request cryptographic verification**.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Email-as-identity, shared data (chosen)** | Cross-device continuity. Minimal infrastructure. Code surface ~15% smaller than ADR 015. Defensible 30-second story. Migration path to OIDC is the same `get_current_user` swap-in. | "Identity" is unverified at the application layer — depends on the network perimeter. Two users typing the same email share preferences. Acceptable in-context, not acceptable on the public internet. |
| UUID-in-`localStorage` (ADR 015, original) | Zero friction. No identity to type. | Doesn't follow users across devices. Supported isolation we don't actually need. |
| Full JWT + password auth | Standard auth pattern. Recognizable to any reviewer. | Login form, password hashing, token expiry, refresh-token strategy, storage-vs-XSS tradeoffs, registration validation — significant additional scope. The downstream DB schema would be identical. |
| Pure shared with no identity at all | Simplest possible. | Can't remember the user's last selection across devices; the assignment requires cross-device continuity. |
| Integrated Windows Authentication / Kerberos SSO | Real "logged-in PC" experience. | Requires server in AD domain, browser configured for the zone, every reviewer to set up Kerberos on their laptop. Not portable. |
| Reverse-proxy SSO header (X-Remote-User from Nginx/Traefik) | The production-correct shape. Headers are injected by a trusted upstream. | Requires the reverse-proxy infrastructure; nothing for a reviewer's `docker compose up` to talk to. |

## Consequences

**Architecture**
- `get_current_user()` is the single source of identity. All routes receive a `User` object.
- `users` has at most one row per distinct email; rows are auto-created on first sight via `INSERT … ON CONFLICT (email) DO NOTHING RETURNING` (race-safe against concurrent first-time-from-same-email).
- Uploads are a shared pool. Concurrent uploads create distinct `upload_id`s in independent transactions and do not conflict — no advisory lock is needed.
- "Activating" a past upload becomes `UPDATE users SET last_viewed_upload_id = ?` — per-user, not global.

**Migration path to production-grade auth**
Replace `get_current_user()` with an OIDC / SAML middleware that injects an IdP-verified `User` row. The `User` object shape (`id`, `email`, `last_viewed_upload_id`, `created_at`) is unchanged. No business-logic layer code is affected. Adding roles / RBAC later is an additive column on `users` + a per-route decorator — no schema rewrite.

**Code surface change relative to ADR 015**
- Dropped: `users.session_token`, `users → uploads` ownership relationship, `uploads.user_id`, `uploads.is_active`, `uploads.set_active`, `UploadNotOwnedError`, per-user advisory lock, the `ix_uploads_user_id` index.
- Added: `users.email` (unique), `users.last_viewed_upload_id` (nullable FK with `ON DELETE SET NULL`), `users.update_last_viewed` repository function.
- Net: roughly 50 fewer lines of repository code, simpler API contract.

**Known gaps explicitly accepted under the deployment-context assumption**
- Anyone who knows another user's corporate email can pose as them via the `X-Session-Token` header. Within an intranet protected by VPN + IdP this is acceptable; on the public internet it is not. The corporate network perimeter is the gating boundary. See `docs/SPEC.md` §0 and `docs/PRODUCTION_ROADMAP.md` §1 for the production swap-in.
- Email format is checked by `pydantic.EmailStr`; no MX/domain verification (handled by the corporate provisioning chain in production).
