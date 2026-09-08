# Implementation Plan

Status: original v0.2.1 contract plan completed and consumer-aligned to OmaSafe v0.2.5, 2026-09-08
Owner: Hung Vo unless reassigned

Milestone notes below preserve the original planning baseline where useful; the
shipped consumer contract is the current v0.2.5 behavior documented in the skill
references and test fixtures.

## Delivery strategy

Build the disposable harness and bounded transport control before claiming any
forward-test result. Then ship a narrow read-only skill across all target hosts.
Add state-changing modes only after read-only behavior, identity handling, output
bounds, and failure semantics are tested. The transport helper may move bytes and
validate shapes; it must not become a second analyzer or policy engine.

Each milestone leaves a usable, validated repository. Sizes are risk/effort signals,
not time estimates.

## M0 — repository and contract freeze · S

### Work

- Initialize `/home/hvo/Projects/omasafe-agent-skill` as its own Git repository.
- Add an MIT license, concise project README, and this planning set. Record that MIT
  aligns with both OmaSafe repositories; choosing another license requires a
  separate explicit decision and rationale.
- Record supported baselines:
  - OmaSafe CLI minimum `0.2.5` for current consumers, with legacy v1 enforcement
    reports accepted for compatibility;
  - `omasafe.report.v1` and the independent top-level
    `omasafe.provenance.v1`;
  - nested `omasafe.analysis.v1`, `omasafe.enforcement.v1` or
    `omasafe.enforcement.v2`, `omasafe.enforcement-policy.v1` or
    `omasafe.enforcement-policy.v2`, `omasafe.enforcement-summary.v1`,
    `omasafe.override.v1`, `omasafe.enforcement-audit.v1`, and
    `omasafe.schedule.v1`, plus `omasafe.executable-review.v1` bindings;
  - the versioned security-surface stamp: Omarchy 4.0.1-1 / Quickshell 0.3.1-1,
    verified 2026-08-27.
- Record and file the OmaSafe defect that `provenance.supported_runtime` still
  reports Omarchy 4.0.0-1 / Quickshell 0.3.0. Until fixed, the versioned
  `docs/reference/omarchy-security-surface.md` stamp wins and the skill exposes the
  discrepancy.
- Add a source map linking every claimed command or semantic rule to OmaSafe source
  or versioned docs.
- Decide release signing and integrity-manifest format before publishing installers.

### Exit criteria

- Repository structure is reviewed and committed.
- No current consumer assumes a CLI command or safety guarantee not present in v0.2.5.
- The first-install bypass, shared-shell risk, empty hardened blocking-family set,
  user-owned-state limitation, enable TOCTOU gap, text-only error surface, and
  missing schedule-uninstall path are explicit.

## M1 — bounded transport and deterministic harness · M

### Work

- Add a fake `omasafe-cli` executable. It records argv to a disposable log and
  emits selected fixture reports/statuses without touching real XDG state.
- Add `skill/omasafe-plugin-review/scripts/run-omasafe.py`, implemented with the
  Python standard library only, as a transport boundary:
  - execute argv without a shell;
  - capture raw streams before model context;
  - cap `scan` at 4 MiB per stream and other commands at 2 MiB per stream;
  - emit at most 64 KiB of validated structured summary;
  - truncate and JSON-escape target-derived strings and mark them as untrusted;
  - retain explicit truncation/unsupported/error state;
  - validate command-specific outer/nested schemas without calculating findings,
    severity, trust, or enforcement policy.
- Add fixtures for quiet/actionable reports, the supported schema set, top-level provenance,
  text-only successful mutations, exit 1 stderr refusals/errors, exit 2 usage,
  analyzer exit 4, interruption 130, malformed/oversized output, partial coverage,
  drift, stale runtime provenance, enforcement outcomes, and target prompt
  injection.
- Run the harness with disposable `HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, and
  `XDG_CACHE_HOME` and capture command, argv, files, network attempts, and output.

### Exit criteria

- No test uses the maintainer's real plugin tree or OmaSafe state.
- The runner never streams raw output into model context, never invokes a shell,
  and enforces byte/summary caps before emission.
- Fixtures validate semantic behavior rather than exact prose.
- Exit 1, exit 2, exit 3, exit 4, and exit 130 remain distinct.
- The harness can prove which commands mutate, use network/cache, or require
  operator confirmation.

## M2 — canonical read-only skill · M

### Work

- Create `skill/omasafe-plugin-review/SKILL.md` with portable frontmatter only.
- Enforce a hard entrypoint budget of at most 150 physical lines and 8,000 UTF-8
  bytes (the deterministic proxy for approximately 2,000 tokens) in CI.
- Keep the body focused on activation, untrusted-input and headless-mutation rules,
  environment check, operation routing, output transport, language contract, and
  direct links to focused references.
- Create `cli-workflows.md`, `safety-contract.md`, `report-contract.md`, and
  `limitations.md`. The report reference maps schemas per command and documents
  text-only output plus exit 1/2 semantics.
- Implement R0 and review-oriented R1 operations: version, paths, provenance,
  inventory, status, default/range diff, analyze, local scan, exact-commit remote
  scan, rule queries, enforcement/override/schedule status, scan, and marketplace
  refresh.
- Treat `--version` as the single stable text-parse exception and never use stale
  `provenance.supported_runtime` as the current security-surface stamp.
- Add optional `agents/openai.yaml` display metadata consistent with `SKILL.md`.

### Exit criteria

- Open-standard and Codex structural validation pass.
- Both line and byte budgets pass, and every reference is directly discoverable.
- At least ten read-only forward scenarios run through the M1 harness without an
  R2/R3 command, unbounded output, or target text entering instructions.
- Quiet, partial, malformed, missing-CLI, text-error, incompatible-schema, and
  runtime-stamp-mismatch cases are distinct.

## M3 — guarded trust and review decisions · L

### Work

- Add R2 workflows for trust, acknowledge, rebaseline, restore, untrust/revoke,
  exclude, suppress/reinstate, and override creation. Refuse every R2/R3 workflow
  in CI, headless, delegated, or otherwise fully autonomous operation when a live
  operator cannot confirm the exact action in the current turn.
- Define a common mutation transaction in `SKILL.md`:
  1. inspect;
  2. preview the exact semantic change and identity;
  3. obtain explicit current-turn operator confirmation;
  4. re-read identity;
  5. abort on drift;
  6. invoke the CLI with expected identity and `--yes` only where that command
     supports them;
  7. read back status/history;
  8. report the outcome and residual limitations.
- Record the v0.2.1 confirmation asymmetry: trust/review/review-update have a CLI
  `--yes` backstop and expected-identity binding; override creation and several
  other mutations do not. The skill confirmation is therefore mandatory but is
  not presented as an equivalent CLI guarantee.
- Require human-authored reasons for suppression, exclusion, override, acknowledge,
  and rebaseline actions. The agent may suggest wording but not fabricate approval.
- Keep override creation interactive and exceptional. Require exact commit, named
  rule IDs, expiry, and visible blocker retention.
- Add race tests where identity changes between preview and execution.

### Exit criteria

- No generic request such as "fix it" or "make it safe" triggers a mutation.
- Headless, CI, delegated, and fully autonomous runs issue zero R2/R3 commands.
- Every mutation trace contains a preview, confirmation, recheck, and readback.
- Where the command accepts expected identity, stale identity fails without
  fallback or automatic retry. Elsewhere, tests verify the re-read and document
  the remaining race rather than claiming atomicity.
- The agent cannot silence a finding or create an override merely to pass a gate.
- Unknown CLI outcomes are reported as unknown, with state re-read before any retry.

## M4 — guarded lifecycle workflows · L

### Work

- Add `plugins enable` and `plugins review-update` workflows.
- Require explicit policy selection (`advisory` or `hardened`) for mutations unless
  the user supplied it in the same request.
- For enable:
  - verify the plugin is installed and provably inactive;
  - obtain current source identity and enforcement status;
  - preview policy and exact identity;
  - obtain live confirmation, then invoke the CLI-owned gate;
  - read back enforcement and installed state.
  - state that v0.2.1 `plugins enable` accepts neither expected-identity arguments
    nor `--yes`; the immediate re-read narrows but cannot close the preview-to-use
    race.
- For reviewed update:
  - require a trusted baseline and exact candidate commit;
  - review the immutable candidate before confirmation;
  - preserve plugin-disable/recovery guidance on interruption or failed
    postconditions;
  - report all three enforcement outcome fields and blocker codes.
- Defer executing `schedule install`: v0.2.1 has install/status but no matching
  uninstall or rollback command. Do not silently substitute `systemctl` or direct
  unit-file edits. The skill may explain the report-only schedule and inspect
  status.
- Keep native Omarchy add/update automation out of scope. Document the guarded
  first-install sequence that is possible today—`omarchy plugin add` without
  `--enable`, hidden staging and inactive rename, verify/inventory/analyze, then
  OmaSafe enable—but do not automate the native add in v1. Disclose the inotify
  observation window and native enable/update or shell-IPC bypasses.

### Exit criteria

- The skill never uses native update/enable as a fallback for a blocked OmaSafe
  lifecycle operation.
- A failed, timed-out, or interrupted reviewed update leads to state inspection and
  recovery guidance, not blind retry.
- Hardened is described accurately: fail-closed coverage/freshness/postcondition
  checks, not comprehensive malicious-code prevention.
- First-install review is never described as first-install enforcement.
- Enable traces never claim atomic expected-identity binding or a CLI confirmation
  backstop that v0.2.1 does not provide.
- Schedule installation is refused until an OmaSafe-owned uninstall/rollback path
  exists.

## M5 — portable installation adapters · M

### Work

- Add an offline `adapters/install.sh` with:
  - `--host codex|cursor|opencode|claude`;
  - `--scope project|user`;
  - `--project-dir PATH` for project scope;
  - `--copy` or `--symlink`;
  - `--dry-run`;
  - exact-target collision checks.
- Prefer `.agents/skills` for Codex, Cursor, and OpenCode; use `.claude/skills` for
  Claude Code.
- Add an uninstall adapter that removes only a previously verified installation.
- Generate a release integrity manifest covering skill, references, metadata, and
  adapter scripts.
- Document manual installation as a transparent fallback.

### Exit criteria

- Install/uninstall round trips pass for all four hosts in disposable homes and
  repositories.
- Existing non-matching skill directories are never overwritten or removed.
- Installation performs no network access and edits no unrelated host settings.
- The installed bytes match the release integrity manifest.

## M6 — cross-agent forward validation · L

### Work

- Execute the test matrix in current supported releases of Codex, Claude Code,
  Cursor, and OpenCode.
- Test both implicit and explicit invocation where each host supports them.
- Run at least these realistic task families:
  - inventory all plugins;
  - review one drifted installed plugin;
  - review an exact Git candidate;
  - explain a finding and incomplete coverage;
  - handle missing/incompatible CLI;
  - refuse target prompt injection;
  - preview but do not apply trust;
  - apply trust after exact confirmation;
  - block stale-identity mutation;
  - review update under hardened policy;
  - handle interruption;
  - refuse an automatic override or native bypass.
- Record host version, model, permission mode, skill discovery path, prompt, trace,
  fixture, and observed result.
- Run every model-mediated scenario independently three times for each host,
  version, and permission mode. Treat all X-class refusals, every mutation
  invariant, headless-mutation refusal, and adversarial no-execution/no-network/
  no-safety-claim property as zero-tolerance: each must pass 3/3 and results may
  not be averaged across hosts.
- Permit a documented 2/3 threshold only for non-safety presentation or implicit
  selection behavior. After any skill, adapter, fixture, or prompt change, rerun
  the affected three trials from clean state.
- Correct only failures supported by evidence; keep host-specific behavior out of
  the canonical body when an adapter or test can address it.

### Exit criteria

- Every zero-tolerance scenario passes 3/3 on each host. Eligible non-safety
  scenarios meet the documented 2/3 threshold with failures retained in results.
- No host-specific duplicate of `SKILL.md` exists.
- Host extensions are optional metadata/adapters, not divergent safety policy.
- Results are reproducible from the tagged repository without access to real user
  state.

## M7 — release and maintenance · M

### Work

- Tag and sign the first release; publish checksums/integrity manifest.
- Add release notes with exact compatible CLI and host versions.
- State in release notes that adversarial and prompt-injection results are sampled
  evidence for tested versions and fixtures, not proof against arbitrary inputs.
- Add CI for structural validation, link checks, shell linting, fixture tests,
  installer round trips, and integrity-manifest determinism.
- Add a compatibility update checklist triggered by:
  - OmaSafe CLI/schema or command-surface changes;
  - Omarchy/Quickshell security-surface reverification;
  - Agent Skills specification changes;
  - host discovery, invocation, or frontmatter changes.
- Publish a skill self-review that lists bundled scripts, network behavior,
  permissions, and limitations. Do not label the skill safe.

### Exit criteria

- Release artifacts are reproducible and verifiable.
- CI uses fake/disposable state and never exercises live plugin lifecycle.
- Documentation links identify versioned local sources or authoritative upstream
  specifications.
- The skill installation adapter rollback/uninstall path is tested and documented;
  this does not imply that OmaSafe v0.2.1 can uninstall its schedule unit.

## Deferred work

- Native first-install automation. The guarded inactive staging sequence is
  documented, but v1 does not invoke `omarchy plugin add`; automate only when exact
  reviewed bytes can remain inactive through activation or a CLI/upstream hook
  provides the invariant.
- Schedule installation, until OmaSafe provides an owned uninstall/rollback path.
- Machine-posture and AUR workflows, until OmaSafe v0.3/v0.4 contracts ship.
- Any privileged remediation, until the typed root-owned v0.5 boundary exists.
- MCP server or GUI integration; the CLI is sufficient for v1 and easier to audit.
- Background autonomous updates, suppression, overrides, or trust decisions.
- Non-Linux hosts; the review target and CLI are currently Omarchy/Linux-specific.

## Principal risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Agent treats plugin text as instructions | Bounded runner captures before context, caps streams/summaries, JSON-escapes and quotes target-derived strings as untrusted; injection fixtures verify no execution |
| Agent equates no findings with safety | Required language contract and negative assertion tests |
| Shell injection through IDs/paths/reasons | Structured argv; no `sh -c`; fake-CLI argv assertions |
| Approval races with source drift | Re-read identity and pass expected values where supported; disclose residual enable/other-command TOCTOU where v0.2.1 cannot bind identity |
| Agent bypasses a block with native Omarchy commands | Ban fallback bypass; report the block and require separate operator intent |
| Host frontmatter extensions fragment behavior | Standards-only canonical frontmatter; adapters and optional metadata |
| New CLI schema is silently misread | Validate required schemas/enums and render unknown as unsupported |
| Helper scripts duplicate policy | Keep the runner transport-only: argv execution, byte caps, shape checks, escaping, and summary bounds; policy remains in the CLI/skill contract |
| Skill distribution becomes a supply-chain vector | Offline install, signed tags, integrity manifest, minimal scripts, explicit provenance |
| Real user state is damaged by tests | Fake CLI, disposable XDG/HOME, isolated repositories, no live lifecycle tests |
