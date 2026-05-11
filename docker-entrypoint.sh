#!/bin/sh
# Container entrypoint: bring the schema up to head, then exec uvicorn.
#
# `exec` replaces the shell with the uvicorn process so SIGTERM from
# `docker stop` reaches uvicorn directly — without it the shell would
# receive the signal and uvicorn would only see SIGKILL after the
# stop-timeout, producing 10-second-slow shutdowns.
#
# `set -e` fails the container if migrations fail rather than starting
# the API against a stale or empty schema.

set -e

echo "Applying database migrations..."
alembic upgrade head

echo "Starting uvicorn on :8000 ..."
exec uvicorn src.api.app:app --host 0.0.0.0 --port 8000
