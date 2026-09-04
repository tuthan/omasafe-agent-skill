#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
skill="$root/skill/omasafe-plugin-review"

[[ -d "$skill" && -f "$skill/SKILL.md" && -f "$skill/agents/openai.yaml" ]]
[[ "$(basename -- "$skill")" == "omasafe-plugin-review" ]]
[[ "$(wc -l < "$skill/SKILL.md")" -le 150 ]]
[[ "$(wc -c < "$skill/SKILL.md")" -le 8000 ]]
grep -q '^---$' "$skill/SKILL.md"
grep -q '^name: omasafe-plugin-review$' "$skill/SKILL.md"
grep -q 'allow_implicit_invocation: true' "$skill/agents/openai.yaml"
for reference in cli-workflows.md safety-contract.md report-contract.md limitations.md; do
  grep -q "references/$reference" "$skill/SKILL.md"
  [[ -f "$skill/references/$reference" ]]
done

python3 "$root/tests/runner_test.py"
python3 "$root/tests/fixture_contract_test.py"
python3 "$root/tests/check_integrity.py"

temp_root=$(mktemp -d)
trap 'rm -rf -- "$temp_root"' EXIT
mkdir -p "$temp_root/project" "$temp_root/home"
project_with_space="$temp_root/project with spaces"
home_with_space="$temp_root/home with spaces"
mkdir -p "$project_with_space" "$home_with_space"
for host in codex cursor opencode claude; do
  if [[ "$host" == claude ]]; then
    project_target="$project_with_space/.claude/skills/omasafe-plugin-review"
  else
    project_target="$project_with_space/.agents/skills/omasafe-plugin-review"
  fi
  [[ ! -e "$project_target" && ! -L "$project_target" ]]
  "$root/adapters/install.sh" --host "$host" --scope project --project-dir "$project_with_space" --copy --dry-run >/dev/null
  [[ ! -e "$project_target" && ! -L "$project_target" ]]
  "$root/adapters/install.sh" --host "$host" --scope project --project-dir "$project_with_space" --copy >/dev/null
  "$root/adapters/uninstall.sh" --host "$host" --scope project --project-dir "$project_with_space" --dry-run >/dev/null
  [[ -d "$project_target" ]]
  "$root/adapters/uninstall.sh" --host "$host" --scope project --project-dir "$project_with_space" >/dev/null
  OMASAFE_INSTALL_HOME="$home_with_space" "$root/adapters/install.sh" --host "$host" --scope user --symlink >/dev/null
  OMASAFE_INSTALL_HOME="$home_with_space" "$root/adapters/uninstall.sh" --host "$host" --scope user >/dev/null
done

mkdir -p "$temp_root/project/.agents/skills/omasafe-plugin-review"
echo "collision" > "$temp_root/project/.agents/skills/omasafe-plugin-review/SKILL.md"
if "$root/adapters/install.sh" --host codex --scope project --project-dir "$temp_root/project" --copy >/dev/null 2>&1; then
  echo "non-matching collision was overwritten" >&2
  exit 1
fi

echo "structural tests: ok"
