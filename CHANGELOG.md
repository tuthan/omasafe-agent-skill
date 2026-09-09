# Changelog

## Unreleased — v0.3.1 posture delta fields

- Documented the three nullable per-check fields `omasafe-cli` 0.3.1 adds to
  `omasafe.posture.v1`: `catalog_index` (the catalog's deliberate, non-alphabetical
  order, which is not the order the `checks` array is emitted in), `previous_state`
  (the preceding report's state; `null` means never observed twice, never
  "unchanged", and a value equal to the current state is a real answer), and
  `gap_open_since`.
- Documented `review_summary.capabilities.by_class`, whose per-class `total` is the
  pre-selection count and so stays exact under report-profile omission. Without it
  an absent class cannot be distinguished from a class whose instances were
  selected away, and must be reported as unknown rather than as none.
- Recorded that pending repository and Omarchy updates report `attention` from
  0.3.1 where earlier versions reported `regression`. The runner preserves the
  state word the installed CLI emits and does not reclassify.

No runner change: the transport already retains additive unknown fields and
validates the schema string rather than a field allowlist, so these reports pass
through unchanged on 0.3.0 and 0.3.1 alike.

## Unreleased — v0.2.5 opaque-code review consumers

- Accepted legacy enforcement v1 and current enforcement v2 reports while
  preserving typed blockers and opaque-code items.
- Added bounded `payload_inventory.code_exposure` transport, omission arithmetic,
  summary reduction, and read-only executable-review ledger validation.
- Documented the interactive, exact-identity `executable-review add|revoke`
  boundary and extended fixtures/tests for the v0.2.5 contract.

## Unreleased — v0.2.4 report consumers

- Preserved review summaries, typed coverage-gap totals, occurrence identities,
  structured evidence steps, behavior context, parser metadata, and presentation
  markers through the bounded transport.
- Validated additive omission arithmetic and kept transport reduction separate from
  CLI selection, including non-prefix review subsets.

## 1.1.1 — 2026-09-04

- Fixed local `scan-plugin --path ... --report-profile review` validation so it
  does not require remote acquisition fields; request, Git, and marketplace
  selectors retain the immutable candidate contract.
- Replaced the all-or-nothing structured-summary fallback with a distinct,
  bounded `summary-reduced` state that keeps ordered finding boundaries,
  severity/location/message evidence, coverage limitations, fingerprints, and
  exact CLI/transport omission arithmetic. Raw stream truncation remains a
  separate state.

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
