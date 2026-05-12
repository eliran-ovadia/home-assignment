# ADR 008: React Frontend Served by FastAPI Static Files

**Date:** 2026-05-09
**Status:** Accepted

## Context

The assignment requires a simple UI that uploads an Excel file and displays positions, violations, and analytics. React was chosen as the frontend framework (preferred by the assignment). The question was how to serve it: as a separate Node.js service, or bundled into the FastAPI container.

## Decision

React is built once via `npm run build` (Vite) and the output (`frontend/dist/`) is served by FastAPI as static files mounted at `/`. All API routes live under `/api/v1/`. The Dockerfile uses **three stages**: (1) `node:20-alpine` runs `npm ci && npm run build` to produce `frontend/dist/`; (2) `python:3.12-slim` builds a `.venv` with the backend deps; (3) a lean `python:3.12-slim` runtime copies the venv plus the built React assets and runs uvicorn. The split keeps the final image small and reproducible.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **React built into FastAPI static files** | Single `docker compose up`, one URL, no CORS config, clean multi-stage Dockerfile | Frontend changes require a rebuild step (acceptable for this scope) |
| Separate Node.js service | Independent dev server with HMR, true separation | Two services to start, CORS headers required, two URLs for the reviewer, more Docker complexity |
| Plain HTML/JS | Simplest possible setup, no build step | Less idiomatic for React; misses the "React preferred" signal in the assignment |

## Consequences

- The reviewer runs one command (`docker compose up`) and gets a fully working system at `http://localhost:8000`.
- No CORS configuration needed anywhere in the codebase.
- Frontend development requires `npm run dev` locally (Vite dev server proxies `/api` to FastAPI) — standard pattern.
- The Dockerfile gains a Node.js build stage, which is a net positive demonstration of multi-stage builds.