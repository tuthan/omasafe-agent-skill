# Changelog

## 1.1.0 — 2026-09-04

- Added v0.2.2 candidate-source routing for raw GitHub URLs, supported copied
  `omarchy plugin add|install` commands, exact Git revisions, and verified
  marketplace IDs.
- Hardened the runner for acquisition/suppression/report-profile invariants,
  redacted pasted requests, 4 MiB `scan-plugin` streams, 120-second remote
  defaults, and bounded analysis totals.
- Documented the immutable scan-only/no-install boundary and archive/registry
  deferral.

## 1.0.0 — 2026-09-04

- Added the canonical `omasafe-plugin-review` Agent Skills package.
- Added bounded, schema-aware `omasafe-cli` transport with disposable fake-CLI tests.
- Added offline copy/symlink installers for Codex, Cursor, OpenCode, and Claude Code.
- Pinned the OmaSafe CLI v0.2.1 contract, report schemas, runtime-stamp discrepancy,
  shared-shell limitations, and guarded mutation workflow.

Forward-testing in the named host applications is not claimed by this repository
until the host/version matrix is run. Adversarial and prompt-injection tests are
sampled evidence for the checked fixtures and versions, not universal proof.
