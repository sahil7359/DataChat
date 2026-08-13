#!/bin/sh
# Container entrypoint for a hosted deploy (Render and friends).
#
# why a script rather than an inline dockerCommand: the platform runs the command
# through a shell, so an inline `sh -c "a && b && c"` gets its quotes passed
# through literally and the shell looks for one command named "a && b && c"
# (exit 127, "not found"). A file has no quoting ambiguity and can be run and
# read locally.
#
# Both steps before the server are idempotent: migrations are versioned, and
# ingestion is checksum-gated, so a redeploy with unchanged data is a no-op.
set -e

echo "==> migrating"
alembic upgrade head

echo "==> seeding"
python -m ingestion.run --dataset seed

echo "==> serving on ${PORT:-8000}"
# exec so uvicorn becomes PID 1 and receives SIGTERM directly — without it the
# shell swallows the signal and the platform waits out its kill timeout on every
# deploy and scale-down.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
