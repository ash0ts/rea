#!/bin/sh
set -eu
example=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "${REA_RECOVERY_PYTHON:-$example/.venv/bin/python}" "$example/scripts/build_containers.py" "$@"
