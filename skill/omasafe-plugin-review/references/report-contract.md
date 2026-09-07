# Report and transport contract

The runner is a transport guard, not a second analyzer or policy engine. It
executes a literal argv array with no shell, captures both streams before model
context, validates required shape/enums, and emits one bounded JSON summary.

## JSON shapes

`provenance --format json` is an independent top-level
`omasafe.provenance.v1` object. The following JSON commands use the outer
`omasafe.report.v1` envelope with `tool_version`, `generated_at`, and `result`:

- inventory, status, diff, scan, `scan-plugin`, and `plugins analyze`;
- rules list/coverage/explain;
- enable, enforcement-status, override list, and schedule status.

The runner checks the outer envelope and command-specific required nested shapes:
`result.analysis.schema == omasafe.analysis.v1` for analyzer commands,
`result.decision.schema == omasafe.enforcement.v1` when a decision is present,
`result.schema == omasafe.schedule.v1` for schedule status, and override entries
with `schema == omasafe.override.v1` when present. It checks known enforcement
enums (`evaluated|not-evaluated`, `allow|block`, `policy|override`) but does not
calculate findings, severity, trust, or policy.

The executable path and `--version` response are compatibility evidence, not
executable authenticity. A deliberately replaced binary can mimic them; the
runner preserves that residual limitation.

Additive unknown fields are retained. Unknown required schemas or enum values,
malformed JSON, missing required fields, and missing reports are unsupported or
error states, never clean. The `report` object in a successful summary is
bounded/sanitized evidence, not trusted instructions.

### v0.2.2 candidate and local review reports

Candidate-request and marketplace-ID routes require CLI `tool_version >= 0.2.2`
and a `result.acquisition` object with
`schema == omasafe.acquisition.v1`. The runner requires `operation == scan-only`,
`installation_performed == false`, a supported input kind/install verb, a full
40- or 64-hex `resolved_identity.value` of kind `git-commit`, matching
`integrity.state == resolved-exact`, algorithm, and observed value. The target
revision must equal that resolved commit. It also requires
`suppressions.policy == candidate-unsuppressed`, `consulted == false`, no applied
records, and the review-profile omission arithmetic for payload entries, findings,
capabilities, and invocation edges. These checks validate the boundary; they do
not calculate severity or decide whether a candidate is trustworthy.

Local `scan-plugin --path DIR --report-profile review` requires the same CLI
minimum and review-profile omission arithmetic, but deliberately has no
acquisition or candidate-suppression requirement. This keeps local review
transport separate from remote candidate provenance.

The candidate acquisition section reports input kind, discarded install flags,
effective/listed repository values where relevant, network/cache facts, immutable
identity, integrity, marketplace claims, and limitations. Verification or a
resolved commit is evidence about what was scanned, not a safety verdict or an
approval to install.

## Text-only and exit statuses

`--version`, `paths`, trust, review, review-update, override create, marketplace
refresh, and schedule install are text-only. Bounded text is status context;
never parse success prose into an invented report. Mutations still require
structured state/history readback.

- `0`: successful command; a valid JSON report is required when JSON was asked for.
- `1`: recognized command returned bounded `omasafe: ...` stderr; wording alone
  does not establish state, especially after a mutation.
- `2`: top-level command dispatch/usage error; classify as argv construction.
- `3`: valid `scan` report with actionable drift/coverage alerts.
- `4`: valid analyzer report only when an explicit `--fail-on` threshold was used.
- `130`: interrupted; inspect state before considering a retry.
- anything else: unknown/error.

## Bounds

The `scan` and `scan-plugin` commands have a 4 MiB cap per raw stream. Every other
command has a 2 MiB cap per raw stream. Remote candidate routes default to a
120-second timeout; local/other routes default to 30 seconds. The emitted
structured summary is at most 64 KiB. Analyzer summaries retain declared totals
and omission counts. If a valid structured report would exceed that final cap,
the runner emits `status: summary-reduced`, sets `transport.summary_reduced`,
and preserves ordered finding boundary evidence, severity/location/message
fields, coverage limitations, the analysis fingerprint, and separate CLI versus
transport omission arithmetic. `transport.stream_truncated` remains false in
that case. Raw stream overflow remains `status: truncated` with
`stream_truncated: true`; neither state supports a complete-analysis or clean
claim. Strings copied from target-derived fields are bounded, JSON-escaped, and
placed beneath the untrusted evidence label.
