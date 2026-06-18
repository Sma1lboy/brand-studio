#!/usr/bin/env sh
set -eu

project="${1:-.}"
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
skill_root=$(CDPATH= cd -- "$script_dir/.." && pwd -P)
project_root=$(CDPATH= cd -- "$project" && pwd -P)

source_missing=""
for path in \
  pyproject.toml \
  src/cli.py \
  src/harness/config.py \
  src/harness/render.py \
  src/harness/publish.py \
  src/harness/style.py
do
  if [ ! -e "$skill_root/$path" ]; then
    source_missing="${source_missing} $path"
  fi
done

project_missing=""
for path in workspace/portfolios workspace/products; do
  if [ ! -e "$project_root/$path" ]; then
    project_missing="${project_missing} $path"
  fi
done

uv_path=$(command -v uv || true)
local_source=1
for path in \
  pyproject.toml \
  src/cli.py \
  src/harness/config.py \
  src/harness/render.py \
  src/harness/publish.py \
  src/harness/style.py
do
  if [ ! -e "$project_root/$path" ]; then
    local_source=0
  fi
done

harness_entrypoint=""
if [ -n "$uv_path" ] && [ "$local_source" -eq 1 ]; then
  harness_entrypoint="uv run harness"
elif [ -n "$uv_path" ]; then
  harness_entrypoint="uv --project $skill_root run harness"
elif [ -x "$skill_root/.venv/bin/harness" ]; then
  harness_entrypoint="$skill_root/.venv/bin/harness"
fi

published_kind="missing"
if [ -f "$project_root/published/.git" ]; then
  published_kind="git-submodule"
elif [ -d "$project_root/published/.git" ]; then
  published_kind="git-repository"
elif [ -d "$project_root/published" ]; then
  published_kind="directory"
fi

if [ -z "$project_missing" ]; then
  project_ready=true
else
  project_ready=false
fi

cat <<EOF
project_root=$project_root
skill_root=$skill_root
source_missing=${source_missing# }
project_missing=${project_missing# }
project_ready=$project_ready
uv_path=$uv_path
harness_entrypoint=$harness_entrypoint
env_exists=$([ -f "$project_root/.env" ] && echo true || echo false)
outputs_exists=$([ -d "$project_root/outputs" ] && echo true || echo false)
published_exists=$([ -d "$project_root/published" ] && echo true || echo false)
published_git_kind=$published_kind
EOF

if [ -n "$source_missing" ] || [ -z "$harness_entrypoint" ]; then
  exit 1
fi
