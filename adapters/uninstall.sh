#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
usage: uninstall.sh --host codex|cursor|opencode|claude --scope project|user
                    [--project-dir PATH] [--dry-run]
EOF
}

host=""
scope=""
project_dir=""
dry_run=0
while (($#)); do
  case "$1" in
    --host) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; host="$2"; shift 2 ;;
    --scope) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; scope="$2"; shift 2 ;;
    --project-dir) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; project_dir="$2"; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$host" in codex|cursor|opencode|claude) ;; *) echo "--host is required and must be codex, cursor, opencode, or claude" >&2; exit 2 ;; esac
case "$scope" in project|user) ;; *) echo "--scope is required and must be project or user" >&2; exit 2 ;; esac

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source_dir=$(cd -- "$script_dir/../skill/omasafe-plugin-review" && pwd -P)
if [[ "$scope" == project ]]; then
  [[ -n "$project_dir" && -d "$project_dir" ]] || { echo "--project-dir must name an existing directory" >&2; exit 1; }
  project_dir=$(cd -- "$project_dir" && pwd -P)
  if [[ "$host" == claude ]]; then
    base_dir="$project_dir/.claude/skills"
  else
    base_dir="$project_dir/.agents/skills"
  fi
else
  install_home="${OMASAFE_INSTALL_HOME:-${HOME:-}}"
  [[ -n "$install_home" && -d "$install_home" ]] || { echo "user home is unavailable; set OMASAFE_INSTALL_HOME" >&2; exit 1; }
  install_home=$(cd -- "$install_home" && pwd -P)
  if [[ "$host" == claude ]]; then
    base_dir="$install_home/.claude/skills"
  else
    base_dir="$install_home/.agents/skills"
  fi
fi

destination="$base_dir/omasafe-plugin-review"
echo "target: $destination"
if [[ ! -e "$destination" && ! -L "$destination" ]]; then
  echo "not installed: $destination"
  exit 0
fi

if [[ -L "$destination" ]]; then
  [[ "$(readlink -f -- "$destination")" == "$source_dir" ]] || { echo "refusing to remove non-matching symlink" >&2; exit 1; }
elif [[ -d "$destination" ]]; then
  diff -qr -- "$source_dir" "$destination" >/dev/null 2>&1 || { echo "refusing to remove non-matching directory" >&2; exit 1; }
else
  echo "refusing to remove non-directory target" >&2
  exit 1
fi

if ((dry_run)); then
  echo "dry-run: no files removed"
else
  rm -rf -- "$destination"
  echo "uninstalled omasafe-plugin-review"
fi
