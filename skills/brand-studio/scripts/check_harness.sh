#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
repo_root=$(CDPATH= cd -- "$script_dir/../../.." && pwd -P)

if [ -x "$repo_root/.venv/bin/python" ]; then
  python_path="$repo_root/.venv/bin/python"
else
  python_path=$(command -v python3 || command -v python || true)
fi

if [ -z "$python_path" ]; then
  echo "check_harness.sh: python3 or python is required" >&2
  exit 1
fi

exec "$python_path" "$script_dir/harness.py" repo check "$@"
