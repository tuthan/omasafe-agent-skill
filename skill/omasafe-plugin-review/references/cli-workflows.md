# OmaSafe CLI workflows

This reference is for routing and command construction. The CLI owns discovery,
identity, analysis, policy, state, and lifecycle semantics.

## Environment

Run `omasafe-cli --version` first through `scripts/run-omasafe.py --`. Accept a
recognized version at or above `0.2.1`; candidate-request, marketplace-ID, and
local review-profile routes require `0.2.2` or newer. Do not run operational commands
after a missing, malformed, or older result. `paths` is read-only text. Use
`provenance --format json` when binary provenance is relevant, but attribute it
to that binary and disclose that v0.2.1 reports an older runtime stamp.

## Read-only and review-oriented commands

Use JSON whenever the command supports it:

```text
plugins inventory --format json
plugins status ID --format json
plugins diff ID --format json
plugins diff ID REF_A..REF_B --format json
plugins analyze ID --format json
scan-plugin --path DIR --format json
scan-plugin --git URL --revision COMMIT --format json
rules list --format json
rules coverage --format json
rules explain RULE_ID --format json
plugins enforcement-status ID --format json
plugins override list --format json
schedule status --format json
scan --include-analysis --format json
```

For a broad estate review, inventory first and use `scan --include-analysis` if
current drift and alert state are requested. Exit 3 with a valid scan report is
an actionable result, not a process failure. A local scan describes the exact
bytes under `DIR`; it does not execute or validate future runtime behavior.

Remote review is a separate network/cache operation. Require an immutable
commit with `--git URL --revision COMMIT`. A branch, moving tag, or “latest” is
not an approval basis. `marketplace refresh --commit COMMIT` is reproducible;
`--latest` is intentionally moving and must be requested explicitly.

For a bounded local review, use `scan-plugin --path DIR --report-profile review
--format json`. This route validates the review profile and its omission
arithmetic but has no remote acquisition or candidate-suppression fields.

## Candidate source review

For a raw public GitHub URL or a copied one-line marketplace command, pass the
complete field as one argv item through the runner:

```text
scan-plugin --request INPUT --report-profile review --format json
```

The CLI, not the agent, parses the finite grammar. Accepted commands are plain
`omarchy plugin add|install URL` with optional `--enable` and `--yes`; those flags
are recorded as discarded install intent. Do not use web/file tools to fetch or
inspect the repository and do not invoke `omarchy` or a shell. The CLI resolves
default-branch HEAD once, fetches the recorded full Git commit into disposable
cache, and analyzes raw objects without checkout, hooks, submodules, filters, or
LFS. Disclose the resolved commit, cache hit/miss, network use, and the
`installation_performed: false` result.

For a legacy marketplace ID, use `scan-plugin --marketplace ID
--report-profile review --format json` only when the CLI has a reverified cached
catalog snapshot. Treat the catalog's verification, age, repository conversion,
and listing commit as attributed claims. The listing's exact validated commit,
not live upstream HEAD, selects bytes. Archive URLs, registry coordinates,
private repositories, and arbitrary installer syntax are unsupported.

The review profile omits payload entries and may cap findings, capabilities, and
invocation edges. Preserve its total/emitted/omitted counts and limitations; an
omitted finding list cannot support an empty-finding conclusion. Full and review
profiles are analysis-equivalent, but only the bounded review profile is intended
for agent/UI transport. If the runner emits `summary-reduced`, use only its
ordered finding boundary evidence, severity/location/message fields, coverage
limitations, fingerprint, and explicit CLI/transport omission arithmetic; it is
not a complete report. Raw `truncated` is a separate stream-overflow state.

## R2 trust and review decisions

For trust, acknowledge, rebaseline, restore, untrust/revoke, exclude,
suppress/reinstate, and override creation:

1. Inventory/status/diff/analyze and identify the exact target and effect.
2. Preview plugin ID, HEAD/tree/content digest, findings, coverage, scope,
   reason, expiry, and resulting semantic state.
3. Ask for targeted current-turn confirmation.
4. Re-read identity. On drift, stop and prepare a new preview.
5. For `trust` and `review`, pass `--yes` only after confirmation and pass every
   available `--expected-head`, `--expected-tree`, and `--expected-digest`.
6. Read status/history after the text-only mutation. Do not invent JSON from
   success prose.

Use `plugins review ID --action ACTION ... --yes` with the documented action and
only the scope/rule/path/to/reason that the operator reviewed. Reasons for
acknowledge, rebaseline, exclusion, and suppression must come from the human;
the agent may suggest text but may not fabricate approval.

Overrides are exceptional: exact commit, named rule IDs, short expiry, human
reason, interactive confirmation, and blocker visibility are required. Never
create a blanket override to make an update pass.

## R3 lifecycle

For `plugins enable ID --policy advisory|hardened`, verify the installed plugin
is provably inactive, inspect identity and enforcement status, preview the
policy and identity, confirm, re-read immediately, invoke the CLI-owned enable,
then read back installed/enforcement state. v0.2.1 provides neither expected
identity arguments nor `--yes` for enable; describe the residual TOCTOU race.

For `plugins review-update ID --expected-commit COMMIT --policy POLICY --yes`,
require a trusted baseline and exact candidate commit, review the immutable
candidate first, confirm the exact commit/digest/policy, then invoke once and
read back status. On failure, timeout, interruption, dirty state, or failed
postconditions, inspect state and give recovery guidance; do not blindly retry.

Do not execute `schedule install` in v1. It has no OmaSafe-owned uninstall or
rollback companion. You may inspect `schedule status` and explain that scheduled
scans are report-only. Do not substitute direct `systemctl` edits.

The possible guarded first-install sequence is documented only: the operator
runs native `omarchy plugin add` without `--enable`, the inactive staged tree is
verified/analyzed, and OmaSafe enable may then be considered. The inotify window,
native lifecycle commands, and raw shell IPC remain bypasses.
