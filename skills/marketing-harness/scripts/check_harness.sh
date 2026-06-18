#!/usr/bin/env sh
set -eu

project="${1:-.}"
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
skill_root=$(CDPATH= cd -- "$script_dir/.." && pwd -P)
project_root=$(CDPATH= cd -- "$project" && pwd -P)
harness_launcher="$skill_root/scripts/harness.py"
python_path=$(command -v python3 || command -v python || true)

project_missing=""
for path in workspace/portfolios workspace/products; do
  if [ ! -e "$project_root/$path" ]; then
    project_missing="${project_missing} $path"
  fi
done

uv_path=$(command -v uv || true)
resolved_harness_command=""
launcher_ready=false
if [ -n "$python_path" ] && [ -f "$harness_launcher" ]; then
  launcher_ready=true
  resolved_harness_command=$("$python_path" "$harness_launcher" --resolve 2>/dev/null || true)
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
project_missing=${project_missing# }
project_ready=$project_ready
python_path=$python_path
uv_path=$uv_path
harness_entrypoint=$python_path $harness_launcher
resolved_harness_command=$resolved_harness_command
launcher_ready=$launcher_ready
env_exists=$([ -f "$project_root/.env" ] && echo true || echo false)
outputs_exists=$([ -d "$project_root/outputs" ] && echo true || echo false)
published_exists=$([ -d "$project_root/published" ] && echo true || echo false)
published_git_kind=$published_kind
EOF

if [ "$launcher_ready" != true ] || [ -z "$resolved_harness_command" ]; then
  exit 1
fi
