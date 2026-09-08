# OmaSafe skill source map

This map records the source for each command and semantic rule claimed by the
portable skill. It is intentionally versioned with the skill and should be
rechecked against the pinned CLI before release.

| Skill claim | Source of truth |
| --- | --- |
| Command names and arguments | `../omasafe/docs/cli-surface.txt`; `../omasafe/crates/omasafe-cli/src/main.rs` |
| Version check and exit 1/2/3/4/130 semantics | `../omasafe/crates/omasafe-cli/src/main.rs` (`main`, command dispatch, scan/analyzer returns) |
| Provenance is top-level | `../omasafe/crates/omasafe-cli/src/main.rs` (`provenance`); `../omasafe/crates/omasafe-cli/tests/cli.rs` (`provenance_report_is_deterministic_and_complete`) |
| Report envelope | `../omasafe/crates/omasafe-report/src/lib.rs` |
| Host posture schema, check states, bounded command adapters, and report retention | `../omasafe/crates/omasafe-posture/src/lib.rs`; `../omasafe/crates/omasafe-cli/src/main.rs` (`posture`) |
| Candidate acquisition schema and exact-commit facts | `../omasafe/crates/omasafe-report/src/acquisition.rs`; `../omasafe/crates/omasafe-cli/src/main.rs` (`scan-plugin`) |
| Analysis schema and evidence fields | `../omasafe/crates/omasafe-report/src/analysis.rs` |
| Enforcement v1/v2 schemas, enums, typed blockers, executable-review policy | `../omasafe/crates/omasafe-report/src/enforcement.rs`; `../omasafe/crates/omasafe-report/src/executable_review.rs` |
| Opaque executable inventory and review status | `../omasafe/crates/omasafe-analyzer/src/payload.rs`; `../omasafe/crates/omasafe-cli/src/main.rs` (`executable_review_list`) |
| Command-to-schema consumption | `../omasafe-plugin/Panel.qml` (`apply*` report handlers); `../omasafe-plugin/model/Candidate.js`; `../omasafe-docs/Plugin/cli-v0.2.1-plan.md` |
| Runtime/shared-shell boundary and reachable bypasses | `../omasafe/docs/reference/omarchy-security-surface.md` |
| Guarded first-install ordering and inotify window | `../omasafe/docs/reference/omarchy-security-surface.md` (Runtime Boundary and H0 answers) |
| v0.2.1 runtime-stamp discrepancy | `../omasafe/crates/omasafe-cli/src/main.rs` (`provenance`); `../omasafe/docs/reference/omarchy-security-surface.md` header |
| Trust/review/executable-review expected identity and confirmation | `../omasafe/crates/omasafe-cli/src/main.rs` (`trust`, `review`, `executable_review_add`); `../omasafe/docs/cli-surface.txt` |
| Enable/review-update asymmetry and recovery | `../omasafe/crates/omasafe-cli/src/main.rs`; `../omasafe/docs/plans/v0.2.1-hardening-implementation.md`; `../omasafe-plugin/Panel.qml` |
| OmaSafe-owned schedule install/uninstall and posture timers | `../omasafe/docs/cli-surface.txt`; `../omasafe/crates/omasafe-cli/src/main.rs` schedule dispatch |
| Portable skill format and validation | `https://agentskills.io/specification`; `/home/hvo/.codex/skills/.system/skill-creator/SKILL.md` |

Relative paths refer to the sibling repositories used for the 2026-09-04
contract freeze. A release built outside this workspace must retain equivalent
versioned upstream links or vendor the checked source references.
