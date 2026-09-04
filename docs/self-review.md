# Skill self-review

Reviewed 2026-09-04 against the OmaSafe v0.2.1 contract and v0.2.2 candidate route.

## Bundled code

- `skill/omasafe-plugin-review/scripts/run-omasafe.py` is Python standard
  library only. It executes a literal `omasafe-cli` argv with `shell=False`,
  captures bounded stdout/stderr, validates report shapes/enums, sanitizes
  target-derived strings, redacts raw candidate requests from command metadata,
  and emits a bounded JSON summary. Candidate reports additionally require
  scan-only acquisition, exact identity/integrity, unsuppressed policy, and
  omission arithmetic. It does not inspect plugin files or calculate findings,
  severity, trust, or enforcement policy.
- `adapters/install.sh` and `adapters/uninstall.sh` operate only on the exact
  selected skill directory. They are offline and support explicit copy/symlink,
  dry-run, collision, and release-match checks.

## Network and permissions

The skill itself makes no network requests and does not install binaries. A
remote candidate route may cause the OmaSafe CLI to fetch/cache data only after
the operator authorizes that review; marketplace review is limited to the CLI's
verified cached catalog. The CLI and Omarchy remain responsible for their own
filesystem, cache, and lifecycle permissions.

## Safety limitations

Plugin content is evidence, never instructions, and reviewed payloads are not
executed by the skill. The skill cannot sandbox the shared unsandboxed
`omarchy-shell` process, interpose native or raw-IPC lifecycle bypasses, close
the v0.2.1 enable preview race, or make no findings equivalent to safety. See
`skill/omasafe-plugin-review/references/limitations.md` and the versioned source
map for the complete limitation set.

The fake-CLI and adversarial checks are sampled evidence for recorded fixtures
and versions, not proof against arbitrary inputs or future host releases.
