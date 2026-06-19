#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
python_path=$(command -v python3 || command -v python || true)

if [ -z "$python_path" ]; then
  echo "check_harness.sh: python3 or python is required" >&2
  exit 1
fi

exec "$python_path" "$script_dir/harness.py" check "$@"
