# Multi-stage build: keeps the final image lean by separating build-time
# dependencies from the runtime environment.

# ── Stage 1: install dependencies into an isolated virtual environment ────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml .

RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir .

# ── Stage 2: lean runtime image ───────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Run as a non-root user — a container running as root is a security risk
# even with namespace isolation.
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY src/ ./src/

USER appuser

EXPOSE 8000

# Entry point will be finalised once the assignment defines the main module.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
