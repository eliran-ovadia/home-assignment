# syntax=docker/dockerfile:1.7
# Three-stage build for a single deployable image. See ADR 008.
#
#   1. frontend-builder — Node Alpine, npm install + npm run build.
#      Output: /build/dist/  (the React bundle: index.html + assets/).
#   2. python-builder    — Python slim, pip install into /opt/venv.
#      Output: /opt/venv/  with every runtime dependency installed.
#   3. runtime           — Python slim, copies (1) + (2) + src + migrations
#      + entrypoint. Runs as a non-root user; uvicorn binds 0.0.0.0:8000.
#
# Image stays lean because build tools (node, npm, pip, gcc) only live in
# the builder stages; the final image only carries the venv and the
# already-compiled static bundle.


# ── Stage 1: build the React frontend ─────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build

# Copy just the manifest first so `npm install` can be cached separately
# from source-code changes. The optional `package-lock.json*` glob lets the
# build succeed even without a lockfile committed (preferred: commit it
# and let `npm ci` give deterministic installs).
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend/ ./
RUN npm run build


# ── Stage 2: install Python dependencies into an isolated venv ────────────────
FROM python:3.12-slim AS python-builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir .


# ── Stage 3: lean runtime ─────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Run as a non-root user — defence in depth even with namespace isolation.
RUN useradd --create-home --shell /bin/sh appuser

WORKDIR /app

# venv from stage 2, app source, migrations + alembic.ini for the
# entrypoint, and the built React bundle from stage 1.
COPY --from=python-builder /opt/venv /opt/venv
COPY --from=frontend-builder /build/dist ./frontend/dist
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini ./

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Default command: serve the API. The `migrate` service in docker-compose.yml
# overrides this with `alembic upgrade head` to run as a one-shot before the
# `app` service starts — same image, two roles. Running this image without
# compose (`docker run …`) will start uvicorn directly; migrate manually
# beforehand if the schema isn't already at head.
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
