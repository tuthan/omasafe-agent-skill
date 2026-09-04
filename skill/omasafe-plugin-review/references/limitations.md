# Known limitations and residual risks

The v0.2.2 candidate route is a read-only Git acquisition and analysis path. It
does not support archives, registry coordinates, private repositories, or native
installation interposition. The CLI resolves a moving GitHub default branch to
one exact commit, but a later native install from the same URL may select a
different commit. The skill cannot guarantee that later action uses the reviewed
bytes.

- OmaSafe v0.2.1 provenance reports `supported_runtime` as Omarchy 4.0.0-1 /
  Quickshell 0.3.0. The verified versioned security-surface stamp is Omarchy
  4.0.1-1 / Quickshell 0.3.1-1 (2026-08-27); expose the discrepancy and use the
  versioned document as the current support reference until the CLI is fixed.
- Omarchy plugins run unsandboxed inside the shared `omarchy-shell` process with
  user permissions. Capabilities are observations, not intent, and the skill is
  not a runtime boundary or a replacement for human review.
- Plugin lifecycle can be reached through native commands and shell IPC. OmaSafe
  does not claim to interpose those bypasses. First-install inactive staging has
  an inotify observation window; a review is not first-install enforcement.
- Hardened policy v0.2.1 still checks coverage, freshness, unsupported executable
  handling, and installed-tree postconditions, but its evidence-gated blocking
  rule-family set is currently empty. It is not comprehensive malicious-code
  prevention.
- `plugins enable` has no `--yes` or expected-identity arguments in v0.2.1. An
  immediate re-read narrows but cannot close its preview-to-use race. Several
  text-only mutations likewise lack a CLI confirmation backstop.
- `schedule install` has no matching OmaSafe uninstall/rollback command, so v1
  reports or inspects schedule state but does not install it.
- OmaSafe state and cache are user-owned. They are useful audit state, not
  tamper-proof evidence after same-user compromise.
- Local or remote analysis covers the exact bytes and analyzer coverage reported
  by the CLI only. A moving branch, future commit, runtime behavior, or an
  unsupported executable is not covered by a clean-looking result. Candidate
  acquisition may write disposable objects below the CLI's analysis cache, but
  it does not write installed plugin, trust, review, override, enable, schedule,
  alert, or notification state.
- Marketplace verification is a snapshot-scoped, attributed claim with age; it
  does not clear local drift or findings. Marketplace-ID scanning is refused when
  the cached catalog cannot be cryptographically reverified and never refreshes
  it silently.
- The review profile is bounded to 1,572,864 serialized UTF-8 bytes. It omits
  payload entries and can omit tails of repeated analysis lists with exact
  counts. An omitted finding list prevents an unqualified no-active-findings
  statement.
- The runner redacts the raw `--request` value from command metadata and bounds
  target-derived report text, but the pasted field remains visible in the active
  UI/input control until that session is closed.
