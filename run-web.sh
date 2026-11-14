#!/bin/sh
# Start the tgflow web panel locally (no docker) for quick iteration.
set -e
cd "$(dirname "$0")"
export TGFLOW_HOME="$(pwd)"
export TGFLOW_PORT="${TGFLOW_PORT:-18319}"
export PYTHONPATH="$(pwd)"
exec .venv/bin/python -m tgflow.web.app
