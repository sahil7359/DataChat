#!/usr/bin/env bash
# mypy --strict wrapper.
#
# On the dev box the uv-managed CPython's _ctypes and mypy's mypyc binaries are
# blocked by a Windows Application Control policy, so a plain `uv run mypy` can't
# even import. When a signed-interpreter tool venv (.venv-mypy) is present we run
# a pure-python mypy from it and point --python-executable at the project venv so
# packages/stubs still resolve. In CI (Linux) that venv is absent and we fall
# back to the normal invocation.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -x ".venv-mypy/Scripts/python.exe" ]; then
  exec .venv-mypy/Scripts/python.exe -m mypy \
    --python-executable "$(pwd)/.venv/Scripts/python.exe" "$@" .
fi

exec uv run mypy "$@" .
