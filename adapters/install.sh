#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
usage: install.sh --host codex|cursor|opencode|claude --scope project|user
                  [--project-dir PATH] [--copy|--symlink] [--replace] [--dry-run]
EOF
}

host=""
scope=""
project_dir=""
mode="copy"
replace=0
dry_run=0

while (($#)); do
  case "$1" in
    --host) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; host="$2"; shift 2 ;;
    --scope) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; scope="$2"; shift 2 ;;
    --project-dir) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; project_dir="$2"; shift 2 ;;
    --copy) mode="copy"; shift ;;
    --symlink) mode="symlink"; shift ;;
    --replace) replace=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$host" in codex|cursor|opencode|claude) ;; *) echo "--host is required and must be codex, cursor, opencode, or claude" >&2; exit 2 ;; esac
case "$scope" in project|user) ;; *) echo "--scope is required and must be project or user" >&2; exit 2 ;; esac

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source_dir=$(cd -- "$script_dir/../skill/omasafe-plugin-review" && pwd -P)
skill_name="omasafe-plugin-review"
[[ -f "$source_dir/SKILL.md" ]] || { echo "source skill is missing: $source_dir" >&2; exit 1; }
grep -q '^name: omasafe-plugin-review$' "$source_dir/SKILL.md" || { echo "source skill name mismatch" >&2; exit 1; }

if [[ "$scope" == project ]]; then
  [[ -n "$project_dir" ]] || { echo "--project-dir is required for project scope" >&2; exit 2; }
  [[ -d "$project_dir" ]] || { echo "project directory is missing or not a directory: $project_dir" >&2; exit 1; }
  project_dir=$(cd -- "$project_dir" && pwd -P)
  if [[ "$host" == claude ]]; then
    base_dir="$project_dir/.claude/skills"
  else
    base_dir="$project_dir/.agents/skills"
  fi
else
  install_home="${OMASAFE_INSTALL_HOME:-${HOME:-}}"
  [[ -n "$install_home" ]] || { echo "user home is unavailable; set OMASAFE_INSTALL_HOME" >&2; exit 1; }
  install_home=$(cd -- "$install_home" && pwd -P)
  if [[ "$host" == claude ]]; then
    base_dir="$install_home/.claude/skills"
  else
    base_dir="$install_home/.agents/skills"
  fi
fi

destination="$base_dir/$skill_name"
echo "source:      $source_dir"
echo "destination: $destination"
echo "mode:        $mode"
if ((dry_run)); then
  echo "dry-run: no files written"
  exit 0
fi

mkdir -p -- "$base_dir"
if [[ -e "$destination" || -L "$destination" ]]; then
  matches=0
  if [[ -L "$destination" ]]; then
    [[ "$(readlink -f -- "$destination")" == "$source_dir" ]] && matches=1
  elif [[ -d "$destination" ]] && diff -qr -- "$source_dir" "$destination" >/dev/null 2>&1; then
    matches=1
  fi
  if ((matches)); then
    echo "already installed: $destination"
    exit 0
  fi
  ((replace)) || { echo "refusing to overwrite non-matching target; pass --replace explicitly" >&2; exit 1; }
  rm -rf -- "$destination"
fi

if [[ "$mode" == symlink ]]; then
  ln -s -- "$source_dir" "$destination"
else
  cp -a -- "$source_dir" "$destination"
fi
echo "installed $skill_name for $host ($scope)"
