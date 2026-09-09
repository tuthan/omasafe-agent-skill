# OmaSafe Agent Skill

> Review what a plugin can do before it touches your shell.

Portable Agent Skills package for reviewing Omarchy plugins through the local
OmaSafe CLI. Version 1.4.0 supports Codex, Cursor, OpenCode, Claude Code, and
compatible hosts through one canonical skill directory. It requires a local
`omasafe-cli` at version 0.3.0 or newer; installing the skill does not install
the CLI or an Omarchy target.

The skill covers v0.2.2 read-only candidate scans, v0.2.4 omission-aware
transport, v0.2.5 opaque-code review evidence and v2 enforcement decisions, and
the additive v0.3.1 posture and capability fields. It does not claim that a
plugin or machine is safe. OmaSafe is not a sandbox, antivirus product, malware
oracle, or replacement for human review.

## Contents

- `skill/omasafe-plugin-review/` — canonical `SKILL.md`, focused references,
  optional Codex metadata, and the bounded `omasafe-cli` transport.
- `adapters/` — offline, exact-target copy/symlink install and uninstall helpers.
- `tests/` — disposable fake-CLI, structural, runner, installer, and integrity checks.
- `../omasafe-docs/Skill/architecture.md`, `../omasafe-docs/Skill/implementation-plan.md`, and
  `../omasafe-docs/Skill/test-matrix.md` — contract and acceptance plan.
- `../omasafe-docs/Skill/source-map.md` — command and semantic claim provenance.
- `../omasafe-docs/Skill/self-review.md` — bundled-code, network, permission, and limitation review.
- `SHA256SUMS` — deterministic release integrity manifest.

## Install

From a checked-out release, run an explicit host and scope. Project scope needs
an existing project directory; user scope uses `OMASAFE_INSTALL_HOME` when set,
otherwise the current user home.

```sh
adapters/install.sh --host codex --scope project --project-dir . --copy
adapters/install.sh --host claude --scope user --symlink
```

Use `--dry-run` to inspect the exact target. Existing non-matching targets are
never overwritten unless `--replace` is supplied. The installer is offline and
does not alter host configuration. Uninstall verifies the target matches the
current release before removing it:

```sh
adapters/uninstall.sh --host codex --scope project --project-dir .
```

Codex, Cursor, and OpenCode use `.agents/skills/omasafe-plugin-review`; Claude
Code uses `.claude/skills/omasafe-plugin-review`. Cloud or remote hosts still
need a deliberately provided `omasafe-cli`; installing instructions alone does
not provide the local binary or Omarchy target.

## Verify

```sh
tests/structural.sh
```

This runs the bounded transport tests, checks the 150-line/8,000-byte entrypoint
budget, verifies the integrity manifest, and exercises copy/symlink install and
uninstall round trips for all four hosts. It uses no network or live OmaSafe
state. The named host forward matrix is not claimed until those applications
are separately tested.

## Safety contract

The CLI owns parsing, identity, findings, severity, coverage, policy, trust, and
lifecycle state. The skill treats all plugin content and report-derived text as
untrusted evidence, never executes reviewed payloads, and requires a live
current-turn operator for R2/R3 mutations. For v0.2.2 candidates it passes a raw
GitHub URL or supported copied install command as one argv item, accepts only the
CLI's immutable acquisition report, and never installs or approves the result.
Unknown, partial, stale, malformed, interrupted, timed-out, and uncertain results
are not clean results. See the canonical skill references for the full workflow.
