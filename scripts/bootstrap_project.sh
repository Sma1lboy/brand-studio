#!/usr/bin/env sh
set -eu

usage() {
  echo "usage: bootstrap_project.sh [--with-example] [target-dir]" >&2
}

with_example=0
target="."

while [ "$#" -gt 0 ]; do
  case "$1" in
    --with-example)
      with_example=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      usage
      exit 2
      ;;
    *)
      target="$1"
      shift
      ;;
  esac
done

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
skill_root=$(CDPATH= cd -- "$script_dir/.." && pwd -P)
mkdir -p "$target"
target_root=$(CDPATH= cd -- "$target" && pwd -P)

mkdir -p \
  "$target_root/workspace/portfolios" \
  "$target_root/workspace/products" \
  "$target_root/outputs" \
  "$target_root/published"

append_line() {
  file="$1"
  line="$2"
  mkdir -p "$(dirname -- "$file")"
  touch "$file"
  if ! grep -qxF "$line" "$file"; then
    printf '%s\n' "$line" >>"$file"
  fi
}

append_line "$target_root/.gitignore" "/.env"
append_line "$target_root/.gitignore" "/outputs/"
append_line "$target_root/.gitignore" "/published/"
append_line "$target_root/.gitignore" "/releases/"

append_line "$target_root/published/.gitattributes" "*.png filter=lfs diff=lfs merge=lfs -text"
append_line "$target_root/published/.gitattributes" "*.jpg filter=lfs diff=lfs merge=lfs -text"
append_line "$target_root/published/.gitattributes" "*.jpeg filter=lfs diff=lfs merge=lfs -text"
append_line "$target_root/published/.gitattributes" "*.webp filter=lfs diff=lfs merge=lfs -text"
append_line "$target_root/published/.gitattributes" "*.gif filter=lfs diff=lfs merge=lfs -text"

copied_examples=""
add_copied_example() {
  if [ -z "$copied_examples" ]; then
    copied_examples="$1"
  else
    copied_examples="$copied_examples $1"
  fi
}

if [ "$with_example" -eq 1 ]; then
  example_workspace="$skill_root/examples/codefox/workspace"
  mkdir -p "$target_root/workspace/portfolios/codefox" "$target_root/workspace/products/codefox"
  if [ -d "$example_workspace/portfolios/codefox" ] && [ ! -e "$target_root/workspace/portfolios/codefox/portfolio.meta.yaml" ]; then
    rm -rf "$target_root/workspace/portfolios/codefox"
    cp -R "$example_workspace/portfolios/codefox" "$target_root/workspace/portfolios/codefox"
    add_copied_example "workspace/portfolios/codefox"
  fi
  if [ -d "$example_workspace/products/codefox/codefox" ] && [ ! -e "$target_root/workspace/products/codefox/codefox" ]; then
    cp -R "$example_workspace/products/codefox/codefox" "$target_root/workspace/products/codefox/codefox"
    add_copied_example "workspace/products/codefox/codefox"
  fi
fi

cat <<EOF
target=$target_root
published_asset_repo=$target_root/published
copied_examples=$copied_examples
EOF
