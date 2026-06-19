#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
python_bin=$(command -v python3 || command -v python || true)

if [ -z "$python_bin" ]; then
  echo "bootstrap_project.sh: python3 or python is required" >&2
  exit 1
fi

exec "$python_bin" "$script_dir/harness.py" bootstrap "$@"
