#!/usr/bin/env python3
"""Bounded, schema-aware transport for omasafe-cli.

This helper deliberately does not inspect plugin files or calculate findings,
severity, trust, or enforcement policy. It only executes a literal argv array,
captures bounded streams, validates the CLI report envelope, and emits a small
JSON summary for an agent.

Usage:
    run-omasafe.py [options] -- <omasafe-cli arguments...>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from typing import Any


SCAN_STREAM_CAP = 4 * 1024 * 1024
OTHER_STREAM_CAP = 2 * 1024 * 1024
SUMMARY_CAP = 64 * 1024
TEXT_CAP = 8 * 1024
STRING_CAP = 2048
ARGV_ITEM_CAP = 512
ARGV_COUNT_CAP = 256
SUMMARY_FINDINGS_CAP = 40
SUMMARY_LIMITATIONS_CAP = 64
SUMMARY_GAPS_CAP = 32
SUMMARY_CODE_EXPOSURE_CAP = 32
SUMMARY_EVIDENCE_STEPS_CAP = 3
SUMMARY_EVIDENCE_FIELD_CAP = 256
SANITIZE_LIST_CAP = 1024

REPORT_SCHEMA = "omasafe.report.v1"
PROVENANCE_SCHEMA = "omasafe.provenance.v1"
ANALYSIS_SCHEMA = "omasafe.analysis.v1"
ENFORCEMENT_SCHEMA = "omasafe.enforcement.v1"
ENFORCEMENT_SCHEMA_V2 = "omasafe.enforcement.v2"
OVERRIDE_SCHEMA = "omasafe.override.v1"
SCHEDULE_SCHEMA = "omasafe.schedule.v1"
POSTURE_SCHEMA = "omasafe.posture.v1"
POSTURE_STATES = {
    "pass", "regression", "attention", "informational", "incomplete",
    "not_applicable", "error",
}
ENFORCEMENT_POLICY_SCHEMA = "omasafe.enforcement-policy.v1"
ENFORCEMENT_POLICY_SCHEMA_V2 = "omasafe.enforcement-policy.v2"
ENFORCEMENT_SUMMARY_SCHEMA = "omasafe.enforcement-summary.v1"
AUDIT_SCHEMA = "omasafe.enforcement-audit.v1"
ACQUISITION_SCHEMA = "omasafe.acquisition.v1"
EXECUTABLE_REVIEW_SCHEMA = "omasafe.executable-review.v1"
EXECUTABLE_REVIEW_POLICY_SCHEMA = "omasafe.executable-review-policy.v1"
REMOTE_CANDIDATE_MIN = (0, 2, 2)
REVIEW_PROFILE_MIN = (0, 2, 2)
EXECUTABLE_REVIEW_MIN = (0, 2, 5)
REMOTE_TIMEOUT = 120.0
# `marketplace refresh --latest` can run several sequential bounded Git
# operations, so it needs an aggregate transport budget rather than the
# ordinary 30-second local-command default.
MARKETPLACE_REFRESH_TIMEOUT = 300.0


def bounded_string(value: Any, limit: int = STRING_CAP) -> str:
    """Bound a string and leave JSON escaping to json.dumps."""
    return str(value)[:limit]


def sanitize(value: Any, depth: int = 0) -> Any:
    """Copy report data into a bounded evidence-only representation."""
    if depth > 24:
        return "[evidence depth omitted]"
    if isinstance(value, str):
        return bounded_string(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list):
        return [sanitize(item, depth + 1) for item in value[:SANITIZE_LIST_CAP]]
    if isinstance(value, dict):
        items = list(value.items())[:256]
        return {bounded_string(key, 256): sanitize(item, depth + 1) for key, item in items}
    return bounded_string(value)


def command_parts(args: list[str]) -> tuple[str, str | None]:
    if not args:
        return "--version", None
    if args[0] in {"--version", "-V"}:
        return args[0], None
    if args[0] == "plugins" and len(args) > 1:
        return f"plugins {args[1]}", args[2] if len(args) > 2 else None
    return args[0], args[1] if len(args) > 1 else None


def parse_version(value: Any) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", str(value or "").strip())
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def has_arg(args: list[str], name: str) -> bool:
    return name in args or any(item.startswith(name + "=") for item in args)


def arg_values(args: list[str], name: str) -> list[str]:
    values: list[str] = []
    for index, item in enumerate(args):
        if item == name and index + 1 < len(args):
            values.append(args[index + 1])
        elif item.startswith(name + "="):
            values.append(item[len(name) + 1 :])
    return values


def is_scan_plugin(args: list[str]) -> bool:
    return bool(args) and args[0] == "scan-plugin"


def is_remote_candidate(args: list[str]) -> bool:
    return is_scan_plugin(args) and any(has_arg(args, name) for name in ("--git", "--request", "--marketplace"))


def is_marketplace_refresh(args: list[str]) -> bool:
    return command_parts(args) == ("marketplace", "refresh")


def is_executable_review(args: list[str]) -> bool:
    return command_parts(args)[0] == "plugins executable-review"


def needs_v022(args: list[str]) -> bool:
    return is_scan_plugin(args) and (is_remote_candidate(args) or has_review_profile(args))


def has_review_profile(args: list[str]) -> bool:
    return is_scan_plugin(args) and "review" in arg_values(args, "--report-profile")


def requires_candidate_contract(args: list[str]) -> bool:
    """Remote selectors need acquisition invariants; local paths do not."""
    return is_remote_candidate(args)


def redact_args(args: list[str]) -> list[str]:
    """Keep argv shape while never emitting the raw pasted request."""
    redacted: list[str] = []
    redact_next = False
    for item in args:
        if redact_next:
            redacted.append("[candidate request omitted]")
            redact_next = False
        elif item == "--request":
            redacted.append(item)
            redact_next = True
        elif item.startswith("--request="):
            redacted.append("--request=[candidate request omitted]")
        else:
            redacted.append(item)
    if redact_next:
        redacted.append("[candidate request omitted]")
    return redacted


def has_json_format(args: list[str]) -> bool:
    try:
        index = args.index("--format")
    except ValueError:
        return False
    return index + 1 < len(args) and args[index + 1] == "json"


def is_text_only(args: list[str]) -> bool:
    command, subcommand = command_parts(args)
    if command in {"--version", "-V", "paths", "marketplace"}:
        return True
    if command == "provenance":
        return not has_json_format(args)
    if command in {"plugins trust", "plugins review", "plugins review-update"}:
        return True
    if command == "plugins executable-review":
        return subcommand in {"add", "revoke"} or not has_json_format(args)
    if command == "plugins override" and subcommand == "create":
        return True
    if command == "schedule" and subcommand == "install":
        return True
    if command == "schedule" and subcommand == "uninstall":
        return True
    if command == "posture":
        return subcommand == "hook" or not has_json_format(args)
    return False


def is_analyzer(args: list[str]) -> bool:
    command, _ = command_parts(args)
    return command in {"plugins analyze", "scan-plugin"}


def _full_commit(value: Any) -> bool:
    return bool(re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", str(value or "")))


def _safe_repository_url(value: Any) -> bool:
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    return bool(re.fullmatch(r"https://[^\s/?#@]+(?:/[^\s?#]*)?", value))


def _bounded_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def validate_review_profile(result: dict[str, Any]) -> str | None:
    profile = result.get("report_profile")
    if not isinstance(profile, dict) or profile.get("name") != "review":
        return "missing or unsupported review report profile"
    limit = _bounded_count(profile.get("serialized_byte_limit"))
    if limit is None or limit <= 0 or limit > 1_572_864:
        return "unsupported review serialized-byte limit"
    analysis = result.get("analysis")
    payload = result.get("payload_inventory")
    omissions = profile.get("omissions")
    if not isinstance(analysis, dict) or not isinstance(payload, dict) or not isinstance(omissions, dict):
        return "review report is missing bounded omission data"
    for name, key in (("payload_entries", "entries"), ("findings", "findings"),
                      ("capabilities", "capabilities"), ("invocation_edges", "invocation_edges"),
                      ("coverage_gaps", "coverage_gaps"), ("code_exposure", "code_exposure")):
        item = omissions.get(name)
        # Older reports predate typed coverage gaps and opaque-code rows; retain
        # their compatibility path while validating each additive field whenever
        # the producer emits it.
        if item is None and ((name == "coverage_gaps" and "coverage_gaps" not in analysis) or
                             (name == "code_exposure" and "code_exposure" not in payload)):
            continue
        if not isinstance(item, dict):
            return f"review report is missing {name} omission data"
        total = _bounded_count(item.get("total"))
        emitted = _bounded_count(item.get("emitted"))
        omitted = _bounded_count(item.get("omitted"))
        if total is None or emitted is None or omitted is None or emitted + omitted != total:
            return f"invalid {name} omission arithmetic"
        if key == "entries":
            entries = payload.get(key)
            if not isinstance(entries, list) or entries:
                return "review report emitted payload entries"
            payload_total = payload.get("totals", {}).get("entries") if isinstance(payload.get("totals"), dict) else None
            if payload_total != total:
                return "payload omission total does not match payload inventory"
        else:
            source = payload if key == "code_exposure" else analysis
            values = source.get(key)
            if not isinstance(values, list) or len(values) != emitted or emitted > SANITIZE_LIST_CAP:
                return f"{key} omission count does not match emitted list"
    evidence_item = omissions.get("evidence_observations")
    if evidence_item is not None:
        total = _bounded_count(evidence_item.get("total")) if isinstance(evidence_item, dict) else None
        emitted = _bounded_count(evidence_item.get("emitted")) if isinstance(evidence_item, dict) else None
        omitted = _bounded_count(evidence_item.get("omitted")) if isinstance(evidence_item, dict) else None
        if total is None or emitted is None or omitted is None or emitted + omitted != total:
            return "invalid evidence_observations omission arithmetic"
    for field, allowed in (
        ("selection_strategy", {"canonical-full-v1", "severity-family-file-round-robin-v1"}),
    ):
        if field in profile and profile[field] not in allowed:
            return f"unsupported review {field}"
    for field in ("presentation_version", "redaction_policy_version"):
        if field in profile and profile[field] != 1:
            return f"unsupported review {field}"
    review_summary = result.get("review_summary")
    if review_summary is not None:
        if not isinstance(review_summary, dict):
            return "review summary is not an object"
        for summary_name, omission_name, active_required in (
            ("findings", "findings", True), ("capabilities", "capabilities", False)
        ):
            summary_counts = review_summary.get(summary_name)
            omission = omissions.get(omission_name)
            if summary_counts is None:
                continue
            if not isinstance(summary_counts, dict) or not isinstance(omission, dict):
                return f"review summary {summary_name} counts are invalid"
            for field in ("emitted", "omitted"):
                if _bounded_count(summary_counts.get(field)) != _bounded_count(omission.get(field)):
                    return f"review summary {summary_name} counts are inconsistent"
            if active_required:
                active = _bounded_count(summary_counts.get("active"))
                suppressed = _bounded_count(summary_counts.get("suppressed"))
                total = _bounded_count(summary_counts.get("total"))
                emitted = _bounded_count(summary_counts.get("emitted"))
                omitted = _bounded_count(summary_counts.get("omitted"))
                if (active is None or suppressed is None or total is None or emitted is None or omitted is None or
                        active != _bounded_count(omission.get("total")) or
                        active + suppressed != total or active != emitted + omitted):
                    return "review summary finding conservation is invalid"
            elif _bounded_count(summary_counts.get("total")) != _bounded_count(omission.get("total")):
                return f"review summary {summary_name} counts are inconsistent"
        if "presentation_complete" in review_summary and not isinstance(review_summary["presentation_complete"], bool):
            return "review summary presentation_complete is invalid"
        suppressions = result.get("suppressions")
        if (isinstance(suppressions, dict) and "suppression_policy" in review_summary and
                review_summary["suppression_policy"] != suppressions.get("policy")):
            return "review summary suppression policy is inconsistent"
    return None


def validate_candidate_report(report: dict[str, Any], args: list[str]) -> str | None:
    """Validate the v0.2.2 candidate boundary without judging findings."""
    tool_version = parse_version(report.get("tool_version"))
    if tool_version is None or tool_version < REMOTE_CANDIDATE_MIN:
        return "candidate route requires omasafe-cli 0.2.2 or newer"
    result = report.get("result")
    if not isinstance(result, dict):
        return "candidate result is not an object"
    acquisition = result.get("acquisition")
    if not isinstance(acquisition, dict) or acquisition.get("schema") != ACQUISITION_SCHEMA:
        return "missing or unsupported candidate acquisition schema"
    if acquisition.get("operation") != "scan-only" or acquisition.get("installation_performed") is not False:
        return "candidate report is not scan-only"
    if acquisition.get("input_kind") not in {"raw-github-url", "omarchy-install-command", "exact-git", "marketplace-id"}:
        return "unsupported candidate input kind"
    if acquisition.get("install_verb") not in {"none", "add", "install"}:
        return "unsupported candidate install verb"
    identity = acquisition.get("resolved_identity")
    integrity = acquisition.get("integrity")
    if not isinstance(identity, dict) or identity.get("kind") != "git-commit" or not _full_commit(identity.get("value")):
        return "candidate report has no full resolved Git commit"
    if not isinstance(integrity, dict) or integrity.get("state") != "resolved-exact":
        return "candidate report has unsupported integrity state"
    expected_algorithm = "git-sha256" if len(identity["value"]) == 64 else "git-sha1"
    if integrity.get("algorithm") != expected_algorithm or integrity.get("observed") != identity["value"]:
        return "candidate integrity does not match the resolved commit"
    if not isinstance(acquisition.get("network_used"), bool):
        return "candidate report has invalid network fact"
    cache = acquisition.get("cache")
    if not isinstance(cache, dict) or not isinstance(cache.get("used"), bool) or cache.get("result") not in {"not-used", "hit", "miss"}:
        return "candidate report has invalid cache fact"
    flags = acquisition.get("discarded_install_flags")
    if not isinstance(flags, list) or any(flag not in {"enable", "yes"} for flag in flags):
        return "candidate report has invalid discarded install flags"
    if not _safe_repository_url(acquisition.get("effective_repository_url")):
        return "candidate report has no safe effective repository URL"
    listed = acquisition.get("listed_repository")
    if listed is not None and not _safe_repository_url(listed):
        return "candidate report has an invalid listed repository"
    claim = acquisition.get("marketplace_claim")
    if acquisition.get("input_kind") == "marketplace-id" and not isinstance(claim, dict):
        return "marketplace candidate attribution is unavailable"
    target = result.get("target")
    if not isinstance(target, dict) or not _full_commit(target.get("revision")) or target.get("revision") != identity["value"]:
        return "candidate target revision is not the resolved commit"
    if target.get("source") not in {"resolved-git-request", "pinned-revision", "marketplace-listing"}:
        return "unsupported candidate target source"
    analysis = result.get("analysis")
    if not isinstance(analysis, dict) or analysis.get("schema") != ANALYSIS_SCHEMA:
        return "missing or unsupported candidate analysis schema"
    suppressions = result.get("suppressions")
    if not isinstance(suppressions, dict) or suppressions.get("policy") != "candidate-unsuppressed" or suppressions.get("consulted") is not False:
        return "candidate suppression policy is not explicit"
    if suppressions.get("applied") != [] or suppressions.get("active_records") is not None:
        return "candidate report contains configured suppression state"
    profile_error = validate_review_profile(result)
    if profile_error:
        return profile_error
    return None


def validate_local_review_report(report: dict[str, Any]) -> str | None:
    """Validate the bounded review profile without requiring remote acquisition."""
    tool_version = parse_version(report.get("tool_version"))
    if tool_version is None or tool_version < REVIEW_PROFILE_MIN:
        return "review profile requires omasafe-cli 0.2.2 or newer"
    result = report.get("result")
    if not isinstance(result, dict):
        return "review result is not an object"
    return validate_review_profile(result)


def validate_executable_review_list(report: dict[str, Any]) -> str | None:
    """Validate the bounded read-only executable-review ledger projection."""
    tool_version = parse_version(report.get("tool_version"))
    if tool_version is None or tool_version < EXECUTABLE_REVIEW_MIN:
        return "executable-review requires omasafe-cli 0.2.5 or newer"
    result = report.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("plugin_id"), str):
        return "executable-review list is missing plugin identity"
    reviews = result.get("reviews")
    if not isinstance(reviews, list) or len(reviews) > 4096:
        return "executable-review list is not bounded"
    for entry in reviews:
        binding = entry.get("binding") if isinstance(entry, dict) else None
        if not isinstance(entry, dict) or not isinstance(binding, dict):
            return "executable-review entry is malformed"
        if binding.get("schema") != EXECUTABLE_REVIEW_SCHEMA:
            return "executable-review binding schema is unsupported"
        if entry.get("status") not in {
                "active", "expired", "rejected", "revoked",
                "no-known-issue", "issue-found", "inconclusive"}:
            return "executable-review entry has an unsupported status"
    return None


def validate_posture_report(report: Any) -> str | None:
    """Validate the raw host posture shape without judging its states."""
    if not isinstance(report, dict) or report.get("schema") != POSTURE_SCHEMA:
        return "unsupported posture schema"
    if report.get("status") == "not_yet_run":
        checks = report.get("checks")
        coverage = report.get("coverage")
        if checks != [] or not isinstance(coverage, dict):
            return "invalid not_yet_run posture report"
        return None
    for field in ("check_catalog_version", "generated_at", "host", "tools", "checks", "coverage"):
        if field not in report:
            return f"posture report missing {field}"
    if not isinstance(report.get("check_catalog_version"), int) or report["check_catalog_version"] < 1:
        return "invalid posture check catalog version"
    if not isinstance(report.get("generated_at"), str):
        return "invalid posture generated_at"
    if not isinstance(report.get("host"), dict) or not isinstance(report.get("tools"), list):
        return "invalid posture host or tools"
    checks = report.get("checks")
    if not isinstance(checks, list) or len(checks) > 4096:
        return "invalid posture checks"
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get("id"), str) or \
                not isinstance(check.get("title"), str) or check.get("state") not in POSTURE_STATES:
            return "invalid posture check state"
        for field in ("evidence", "dependencies", "limitations"):
            if not isinstance(check.get(field), list):
                return f"invalid posture check {field}"
    coverage = report.get("coverage")
    if not isinstance(coverage, dict):
        return "invalid posture coverage"
    for field in ("complete", "incomplete", "errors", "not_applicable"):
        value = _bounded_count(coverage.get(field))
        if value is None:
            return f"invalid posture coverage {field}"
    if not isinstance(coverage.get("limitations"), list):
        return "invalid posture coverage limitations"
    age = report.get("result_age_seconds")
    if age is not None and (_bounded_count(age) is None):
        return "invalid posture result age"
    return None


def analysis_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    result = report.get("result")
    analysis = result.get("analysis") if isinstance(result, dict) else None
    if not isinstance(analysis, dict):
        return None
    payload = result.get("payload_inventory") if isinstance(result, dict) else None
    profile = result.get("report_profile") if isinstance(result, dict) else None
    omissions = profile.get("omissions") if isinstance(profile, dict) else {}
    totals: dict[str, dict[str, int]] = {}
    for key in ("findings", "capabilities", "invocation_edges", "coverage_gaps"):
        item = omissions.get(key) if isinstance(omissions, dict) else None
        values = analysis.get(key)
        emitted = len(values) if isinstance(values, list) else 0
        if isinstance(item, dict):
            total = _bounded_count(item.get("total"))
            omitted = _bounded_count(item.get("omitted"))
            if total is not None and omitted is not None:
                profile_emitted = _bounded_count(item.get("emitted"))
                if profile_emitted is not None:
                    emitted = profile_emitted
                totals[key] = {"total": total, "emitted": emitted, "omitted": omitted}
                continue
        totals[key] = {"total": emitted, "emitted": emitted, "omitted": 0}
    summary: dict[str, Any] = {
        **totals,
        "coverage_limitations": len(analysis.get("coverage_limitations", [])) if isinstance(analysis.get("coverage_limitations"), list) else 0,
        "analysis_fingerprint": bounded_string(analysis.get("analysis_fingerprint", ""), 128),
    }
    code_exposure = payload.get("code_exposure") if isinstance(payload, dict) else None
    code_item = omissions.get("code_exposure") if isinstance(omissions, dict) else None
    code_emitted = len(code_exposure) if isinstance(code_exposure, list) else 0
    code_total = code_emitted
    code_omitted = 0
    if isinstance(code_item, dict):
        maybe_total = _bounded_count(code_item.get("total"))
        maybe_emitted = _bounded_count(code_item.get("emitted"))
        maybe_omitted = _bounded_count(code_item.get("omitted"))
        if maybe_total is not None and maybe_emitted is not None and maybe_omitted is not None:
            code_total, code_emitted, code_omitted = maybe_total, maybe_emitted, maybe_omitted
    if isinstance(code_exposure, list) or isinstance(code_item, dict):
        summary["code_exposure"] = {
            "total": code_total, "emitted": code_emitted, "omitted": code_omitted
        }
    evidence_item = omissions.get("evidence_observations") if isinstance(omissions, dict) else None
    if isinstance(evidence_item, dict):
        total = _bounded_count(evidence_item.get("total"))
        emitted = _bounded_count(evidence_item.get("emitted"))
        omitted = _bounded_count(evidence_item.get("omitted"))
        if total is not None and emitted is not None and omitted is not None:
            summary["evidence_observations"] = {"total": total, "emitted": emitted, "omitted": omitted}
    review_summary = result.get("review_summary") if isinstance(result, dict) else None
    if isinstance(review_summary, dict):
        summary["review_summary"] = compact_review_summary(review_summary)
        summary["freshness"] = bounded_string(review_summary.get("freshness", "unknown"), 64)
        summary["presentation_complete"] = review_summary.get("presentation_complete") is True
        summary["coverage_assessment"] = bounded_string(
            review_summary.get("coverage", {}).get("assessment", "unknown")
            if isinstance(review_summary.get("coverage"), dict) else "unknown", 64
        )
        summary["untrusted_data_notice"] = bounded_string(
            review_summary.get("untrusted_data_notice", ""), SUMMARY_EVIDENCE_FIELD_CAP
        )
    return summary


def posture_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    """Keep bounded posture state/coverage context beside the raw evidence."""
    if not isinstance(report, dict) or report.get("schema") != POSTURE_SCHEMA:
        return None
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    states: dict[str, int] = {}
    for check in checks:
        if isinstance(check, dict) and isinstance(check.get("state"), str):
            state = check["state"]
            states[state] = states.get(state, 0) + 1
    result: dict[str, Any] = {
        "status": bounded_string(report.get("status", "complete"), 64),
        "check_count": len(checks),
        "states": states,
        "coverage": compact_fields(
            report.get("coverage"), ("complete", "incomplete", "errors", "not_applicable")
        ),
        "generated_at": bounded_string(report.get("generated_at", ""), 128),
    }
    if "result_age_seconds" in report:
        result["result_age_seconds"] = report["result_age_seconds"]
    host = report.get("host")
    if isinstance(host, dict):
        result["host"] = compact_fields(host, ("os", "arch", "omarchy_version", "kernel"))
    return result


def validate_report(report: Any, args: list[str]) -> tuple[bool, str | None]:
    """Validate transport shape only; never calculate security semantics."""
    command, subcommand = command_parts(args)
    if command == "posture":
        if subcommand not in {"scan", "export", "digest"} or not has_json_format(args):
            return False, "unsupported posture JSON route"
        posture_error = validate_posture_report(report)
        return posture_error is None, posture_error
    if command == "provenance":
        if not isinstance(report, dict) or report.get("schema") != PROVENANCE_SCHEMA:
            return False, "unsupported provenance schema"
        if not isinstance(report.get("tool_version"), str):
            return False, "provenance missing tool_version"
        return True, None

    if not isinstance(report, dict) or report.get("schema") != REPORT_SCHEMA:
        return False, "unsupported report envelope"
    if not isinstance(report.get("tool_version"), str):
        return False, "report missing tool_version"
    if not isinstance(report.get("generated_at"), str):
        return False, "report missing generated_at"
    result = report.get("result")
    if not isinstance(result, dict):
        return False, "report result is not an object"

    if is_analyzer(args):
        analysis = result.get("analysis")
        if not isinstance(analysis, dict) or analysis.get("schema") != ANALYSIS_SCHEMA:
            return False, "missing or unsupported analysis schema"
        for field in ("findings", "capabilities", "invocation_edges", "coverage_limitations"):
            if not isinstance(analysis.get(field), list):
                return False, f"analysis field {field} is not a list"
        if "coverage_gaps" in analysis and not isinstance(analysis.get("coverage_gaps"), list):
            return False, "analysis field coverage_gaps is not a list"

    if command in {"plugins enable", "plugins enforcement-status"}:
        if "decision" not in result:
            return False, "missing enforcement decision"
        decision = result.get("decision")
        if decision is not None:
            if not isinstance(decision, dict) or decision.get("schema") not in {
                    ENFORCEMENT_SCHEMA, ENFORCEMENT_SCHEMA_V2}:
                return False, "unsupported enforcement decision"
            if decision.get("schema") == ENFORCEMENT_SCHEMA_V2:
                for field in ("blockers", "opaque_code_items"):
                    if not isinstance(decision.get(field), list) or len(decision[field]) > 4096:
                        return False, f"invalid enforcement v2 {field}"
                if decision.get("executable_review_policy_version") != EXECUTABLE_REVIEW_POLICY_SCHEMA:
                    return False, "invalid enforcement v2 executable-review policy"
            enum_fields = {
                "evaluation_state": {"evaluated", "not-evaluated"},
                "outcome": {"allow", "block"},
                "authorization_basis": {None, "policy", "override"},
            }
            for field, allowed in enum_fields.items():
                if field in decision and decision[field] not in allowed:
                    return False, f"unsupported enforcement enum {field}"

    if command == "schedule" and subcommand == "status":
        if result.get("schema") != SCHEDULE_SCHEMA:
            return False, "unsupported schedule schema"

    if command == "plugins override" and subcommand == "list":
        if not isinstance(result.get("overrides"), list):
            return False, "override list is not a list"
        for entry in result["overrides"]:
            if not isinstance(entry, dict):
                return False, "unsupported override entry"
            binding = entry.get("binding", entry)
            if not isinstance(binding, dict) or binding.get("schema") != OVERRIDE_SCHEMA:
                return False, "unsupported override binding"

    if is_executable_review(args) and subcommand == "list":
        review_error = validate_executable_review_list(report)
        if review_error:
            return False, review_error

    if command == "rules" and subcommand == "coverage":
        if not isinstance(result.get("coverage"), list) or "map_version" not in result:
            return False, "unsupported coverage report"

    if requires_candidate_contract(args):
        if not isinstance(report, dict):
            return False, "candidate report is not an object"
        candidate_error = validate_candidate_report(report, args)
        if candidate_error:
            return False, candidate_error
    elif has_review_profile(args):
        if not isinstance(report, dict):
            return False, "review report is not an object"
        review_error = validate_local_review_report(report)
        if review_error:
            return False, review_error

    nested_schemas = {
        "enforcement_summary": ENFORCEMENT_SUMMARY_SCHEMA,
        "enforcement_policy": {ENFORCEMENT_POLICY_SCHEMA, ENFORCEMENT_POLICY_SCHEMA_V2},
        "audit": AUDIT_SCHEMA,
        "audit_event": AUDIT_SCHEMA,
    }
    for field, schema in nested_schemas.items():
        if field in result and result[field] is not None:
            nested = result[field]
            if not isinstance(nested, dict) or nested.get("schema") not in (
                    schema if isinstance(schema, set) else {schema}):
                return False, f"unsupported {field} schema"

    return True, None


def kill_process(proc: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, OSError):
        pass


def capture(proc: subprocess.Popen[bytes], cap: int, timeout: float) -> tuple[bytes, bytes, dict[str, Any]]:
    """Read both pipes with caps, without communicate()'s unbounded buffering."""
    selector = selectors.DefaultSelector()
    streams: dict[int, bytearray] = {}
    handles: list[Any] = []
    for stream in (proc.stdout, proc.stderr):
        assert stream is not None
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ)
        streams[stream.fileno()] = bytearray()
        handles.append(stream)

    started = time.monotonic()
    timed_out = False
    stream_truncated = False
    aborted = False
    while selector.get_map():
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            timed_out = True
            aborted = True
            kill_process(proc)
            break
        for key, _ in selector.select(min(remaining, 0.25)):
            fd = key.fd
            current = streams[fd]
            read_size = min(65536, max(1, cap - len(current) + 1))
            try:
                data = os.read(fd, read_size)
            except BlockingIOError:
                continue
            if not data:
                selector.unregister(key.fileobj)
                key.fileobj.close()
                continue
            if len(current) + len(data) > cap:
                current.extend(data[: cap - len(current)])
                stream_truncated = True
                aborted = True
                kill_process(proc)
                break
            current.extend(data)
        if aborted:
            break

    if aborted:
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            kill_process(proc)
            proc.wait(timeout=2)
        for stream in handles:
            try:
                stream.close()
            except OSError:
                pass
        selector.close()
    else:
        selector.close()
        remaining_wait = max(0.0, timeout - (time.monotonic() - started))
        try:
            proc.wait(timeout=remaining_wait)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_process(proc)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                kill_process(proc)

    # File descriptors are closed on EOF/abort, so use the stable insertion
    # order captured above rather than asking the Popen streams for their fd.
    ordered = list(streams.values())
    return bytes(ordered[0]), bytes(ordered[1]), {
        "timed_out": timed_out,
        "stream_truncated": stream_truncated,
        "stdout_bytes": len(ordered[0]),
        "stderr_bytes": len(ordered[1]),
    }


def exit_code(proc: subprocess.Popen[bytes]) -> int | None:
    code = proc.returncode
    if code is None:
        return None
    return 128 + (-code) if code < 0 else code


def text_from_bytes(data: bytes, limit: int = TEXT_CAP) -> str:
    return bounded_string(data.decode("utf-8", errors="replace"), limit)


def compact_fields(value: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for field in fields:
        if field in value:
            item = value[field]
            if isinstance(item, str):
                result[field] = bounded_string(item, SUMMARY_EVIDENCE_FIELD_CAP)
            elif isinstance(item, (bool, int, float)) or item is None:
                result[field] = item
    return result


def compact_count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, item in list(value.items())[:64]:
        count = _bounded_count(item)
        if count is not None:
            result[bounded_string(key, SUMMARY_EVIDENCE_FIELD_CAP)] = count
    return result


def compact_count_rows(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key, item in list(value.items())[:64]:
        if isinstance(item, dict):
            row = compact_fields(item, ("rule_id", "total", "active", "suppressed", "emitted", "omitted"))
            for field in ("total", "active", "suppressed", "emitted", "omitted"):
                if field in row and _bounded_count(row[field]) is None:
                    row.pop(field, None)
            result[bounded_string(key, SUMMARY_EVIDENCE_FIELD_CAP)] = row
        else:
            count = _bounded_count(item)
            if count is not None:
                result[bounded_string(key, SUMMARY_EVIDENCE_FIELD_CAP)] = count
    return result


def compact_summary_counts(value: Any, include_active: bool) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = compact_fields(value, ("total", "active", "suppressed", "emitted", "omitted"))
    for field in ("total", "active", "suppressed", "emitted", "omitted"):
        if field in result and _bounded_count(result[field]) is None:
            result.pop(field, None)
    if include_active:
        result["by_severity"] = compact_count_rows(value.get("by_severity"))
        result["by_rule"] = compact_count_rows(value.get("by_rule"))
    return result


def compact_review_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = compact_fields(value, (
        "schema", "policy_identity_digest", "analysis_produced_at", "freshness",
        "source_identity_ref", "source_identity_state", "presentation_complete",
        "suppression_policy", "suppression_reconfirmation_count", "untrusted_data_notice",
    ))
    if isinstance(value.get("findings"), dict):
        result["findings"] = compact_summary_counts(value["findings"], True)
    if isinstance(value.get("capabilities"), dict):
        result["capabilities"] = compact_summary_counts(value["capabilities"], False)
    if isinstance(value.get("coverage"), dict):
        coverage = value["coverage"]
        result["coverage"] = compact_fields(coverage, (
            "assessment", "gap_total", "executable_or_load_gaps", "language_model_gaps",
            "inert_metadata_entries",
        ))
        result["coverage"]["payload_states"] = compact_count_map(coverage.get("payload_states"))
        result["coverage"]["by_reason"] = compact_count_map(coverage.get("by_reason"))
    for field in ("findings_before_suppression", "max_severity", "threshold_breached", "complete"):
        if field in value:
            item = value[field]
            if isinstance(item, str):
                result[field] = bounded_string(item, SUMMARY_EVIDENCE_FIELD_CAP)
            elif isinstance(item, (bool, int, float)) or item is None:
                result[field] = item
    if isinstance(value.get("coverage_gaps"), dict):
        result["coverage_gaps"] = compact_summary_counts(value["coverage_gaps"], False)
    if isinstance(value.get("severity_counts"), dict):
        result["severity_counts"] = compact_count_map(value["severity_counts"])
    if isinstance(value.get("rule_counts"), dict):
        result["rule_counts"] = compact_count_map(value["rule_counts"])
    if isinstance(value.get("presentation_collections"), dict):
        result["presentation_collections"] = compact_count_rows(value["presentation_collections"])
    if isinstance(value.get("threshold"), dict):
        result["threshold"] = compact_fields(value["threshold"], ("requested", "breached"))
    if isinstance(value.get("lifecycle_policy"), dict):
        result["lifecycle_policy"] = compact_fields(
            value["lifecycle_policy"], ("evaluation_state", "outcome", "authorization_basis")
        )
    return result


def compact_evidence_step(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"value": bounded_string(value, SUMMARY_EVIDENCE_FIELD_CAP)}
    return compact_fields(value, (
        "id", "role", "relative_path", "display_relative_path", "line", "column",
        "analysis_method", "detail", "origin", "redacted", "truncated",
    ))


def compact_finding(value: Any) -> dict[str, Any]:
    """Keep identity, severity, location, and concise structured evidence in order."""
    if not isinstance(value, dict):
        return {"value": bounded_string(value, SUMMARY_EVIDENCE_FIELD_CAP)}
    result = compact_fields(value, (
        "id", "key", "occurrence_id", "rule_id", "rule_semantic_identity_digest",
        "severity", "title", "relative_path", "display_relative_path", "line", "column",
        "analysis_method", "message", "evidence", "evidence_summary", "explanation",
    ))
    if isinstance(value.get("evidence_summary"), dict):
        result["evidence_summary"] = compact_fields(
            value["evidence_summary"], ("total", "emitted", "omitted", "observation_collection_complete")
        )
    steps = value.get("evidence_steps")
    if isinstance(steps, list):
        kept = steps[:SUMMARY_EVIDENCE_STEPS_CAP]
        result["evidence_steps"] = [compact_evidence_step(item) for item in kept]
        if len(steps) > len(kept):
            result["evidence_steps_omitted"] = len(steps) - len(kept)
    context = value.get("behavior_context")
    if isinstance(context, dict):
        result["behavior_context"] = compact_fields(context, (
            "connection", "source_class", "sink_kind", "sink_argument_role", "trigger",
        ))
        if isinstance(context.get("destination"), dict):
            result["behavior_context"]["destination"] = compact_fields(
                context["destination"], ("scheme", "host", "port", "path_display", "dynamic", "redacted")
            )
    if isinstance(value.get("presentation"), dict):
        presentation = compact_fields(value["presentation"], ("redacted", "truncated"))
        for field in ("redaction_classes", "omitted_fields"):
            items = value["presentation"].get(field)
            if isinstance(items, list):
                presentation[field] = [bounded_string(item, SUMMARY_EVIDENCE_FIELD_CAP) for item in items[:16]]
        result["presentation"] = presentation
    return result


def compact_limitation(value: Any) -> Any:
    if isinstance(value, str):
        return bounded_string(value, SUMMARY_EVIDENCE_FIELD_CAP)
    if isinstance(value, dict):
        return compact_fields(value, (
            "code", "kind", "reason", "message", "detail", "path", "relative_path",
        ))
    return bounded_string(value, SUMMARY_EVIDENCE_FIELD_CAP)


def compact_gap(value: Any) -> Any:
    if not isinstance(value, dict):
        return bounded_string(value, SUMMARY_EVIDENCE_FIELD_CAP)
    result = compact_fields(value, (
        "reason", "language", "relative_path", "display_relative_path", "line", "impact", "detail",
    ))
    rule_ids = value.get("rule_ids")
    if isinstance(rule_ids, list):
        result["rule_ids"] = [bounded_string(item, SUMMARY_EVIDENCE_FIELD_CAP) for item in rule_ids[:32]]
    return result


def compact_code_exposure(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"value": bounded_string(value, SUMMARY_EVIDENCE_FIELD_CAP)}
    return compact_fields(value, (
        "relative_path", "native_format", "exact_sha256", "digest_state",
        "exposure", "content_class", "opaque_review_required", "review_status",
    ))


def report_omission_counts(result: dict[str, Any], name: str, field: str) -> tuple[int, int, int]:
    """Return total, CLI-emitted, CLI-omitted counts from a validated report."""
    source = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
    if field == "code_exposure":
        source = result.get("payload_inventory") if isinstance(result.get("payload_inventory"), dict) else {}
    values = source.get(field)
    actual = len(values) if isinstance(values, list) else 0
    profile = result.get("report_profile")
    omissions = profile.get("omissions") if isinstance(profile, dict) else None
    item = omissions.get(name) if isinstance(omissions, dict) else None
    if isinstance(item, dict):
        total = _bounded_count(item.get("total"))
        emitted = _bounded_count(item.get("emitted"))
        omitted = _bounded_count(item.get("omitted"))
        if total is not None and emitted is not None and omitted is not None and emitted + omitted == total:
            return total, emitted, omitted
    return actual, actual, 0


def reduction_counts(total: int, cli_emitted: int, cli_omitted: int, kept: int) -> dict[str, int]:
    transport_omitted = max(0, cli_emitted - kept)
    return {
        "total": total,
        "emitted": kept,
        "omitted": cli_omitted + transport_omitted,
        "cli_emitted": cli_emitted,
        "cli_omitted": cli_omitted,
        "transport_emitted": kept,
        "transport_omitted": transport_omitted,
    }


def bounded_ordered_items(values: list[Any], limit: int) -> list[Any]:
    """Keep both boundaries while preserving the CLI's relative order."""
    if len(values) <= limit:
        return values
    head = limit // 2
    return values[:head] + values[-(limit - head):]


def compact_candidate_context(result: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    target = result.get("target")
    if isinstance(target, dict):
        compact["target"] = compact_fields(target, ("source", "url", "revision", "scope", "root"))
    acquisition = result.get("acquisition")
    if isinstance(acquisition, dict):
        compact["acquisition"] = compact_fields(acquisition, (
            "schema", "operation", "installation_performed", "input_kind", "install_verb",
            "requested_reference", "network_used", "listed_repository",
            "effective_repository_url",
        ))
        for field in ("resolved_identity", "integrity", "cache"):
            if isinstance(acquisition.get(field), dict):
                compact["acquisition"][field] = compact_fields(
                    acquisition[field], tuple(acquisition[field].keys())
                )
        if isinstance(acquisition.get("discarded_install_flags"), list):
            compact["acquisition"]["discarded_install_flags"] = [
                bounded_string(item, SUMMARY_EVIDENCE_FIELD_CAP)
                for item in acquisition["discarded_install_flags"][:32]
            ]
    suppressions = result.get("suppressions")
    if isinstance(suppressions, dict):
        compact["suppressions"] = compact_fields(
            suppressions, ("policy", "consulted", "active_records")
        )
        compact["suppressions"]["applied"] = []
    return compact


def reduce_analysis_report(report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Make a small evidence report after the raw report exceeds the summary cap."""
    result = report.get("result")
    analysis = result.get("analysis") if isinstance(result, dict) else None
    if not isinstance(result, dict) or not isinstance(analysis, dict):
        return None
    findings = analysis.get("findings") if isinstance(analysis.get("findings"), list) else []
    limitations = analysis.get("coverage_limitations") if isinstance(analysis.get("coverage_limitations"), list) else []
    coverage_gaps = analysis.get("coverage_gaps") if isinstance(analysis.get("coverage_gaps"), list) else []
    payload = result.get("payload_inventory") if isinstance(result.get("payload_inventory"), dict) else {}
    code_exposure = payload.get("code_exposure") if isinstance(payload.get("code_exposure"), list) else []
    finding_total, finding_cli_emitted, finding_cli_omitted = report_omission_counts(
        result, "findings", "findings"
    )
    limitation_total = len(limitations)
    gap_total, gap_cli_emitted, gap_cli_omitted = report_omission_counts(
        result, "coverage_gaps", "coverage_gaps"
    )
    code_total, code_cli_emitted, code_cli_omitted = report_omission_counts(
        result, "code_exposure", "code_exposure"
    )
    finding_items = [compact_finding(item) for item in bounded_ordered_items(findings, SUMMARY_FINDINGS_CAP)]
    limitation_items = [compact_limitation(item) for item in bounded_ordered_items(limitations, SUMMARY_LIMITATIONS_CAP)]
    gap_items = [compact_gap(item) for item in bounded_ordered_items(coverage_gaps, SUMMARY_GAPS_CAP)]
    code_items = [compact_code_exposure(item) for item in bounded_ordered_items(
        code_exposure, SUMMARY_CODE_EXPOSURE_CAP
    )]
    finding_counts = reduction_counts(
        finding_total, finding_cli_emitted, finding_cli_omitted, len(finding_items)
    )
    limitation_counts = reduction_counts(
        limitation_total, limitation_total, 0, len(limitation_items)
    )
    gap_counts = reduction_counts(gap_total, gap_cli_emitted, gap_cli_omitted, len(gap_items))
    code_counts = reduction_counts(code_total, code_cli_emitted, code_cli_omitted, len(code_items))

    compact_analysis: dict[str, Any] = {
        "schema": analysis.get("schema"),
        "analysis_fingerprint": bounded_string(analysis.get("analysis_fingerprint", ""), 128),
        "findings": finding_items,
        "capabilities": [],
        "invocation_edges": [],
        "coverage_limitations": limitation_items,
        "coverage_gaps": gap_items,
    }
    policy_identity = analysis.get("policy_identity")
    if isinstance(policy_identity, dict):
        compact_analysis["policy_identity"] = compact_fields(
            policy_identity, ("analyzer_version", "policy_id", "profile")
        )
    parsers = analysis.get("parsers")
    if isinstance(parsers, dict):
        compact_analysis["parsers"] = {
            bounded_string(language, SUMMARY_EVIDENCE_FIELD_CAP): compact_fields(
                parser, ("method", "grammar", "grammar_version", "runtime_version")
            )
            for language, parser in list(parsers.items())[:32]
            if isinstance(parser, dict)
        }
    review_summary = result.get("review_summary")
    if isinstance(review_summary, dict):
        compact_result_review = compact_review_summary(review_summary)
    else:
        compact_result_review = None
    compact_result: dict[str, Any] = compact_candidate_context(result)
    if isinstance(payload, dict):
        compact_result["payload_inventory"] = {
            "code_exposure": code_items,
            "coverage_states": compact_count_map(payload.get("coverage_states")),
            "entries": [],
        }
    for field in ("plugin_id", "id"):
        if field in result:
            compact_result[field] = bounded_string(result[field], SUMMARY_EVIDENCE_FIELD_CAP)
    profile = result.get("report_profile")
    if isinstance(profile, dict):
        compact_result["report_profile"] = {
            "name": profile.get("name"),
            "serialized_byte_limit": profile.get("serialized_byte_limit"),
            "selection_strategy": profile.get("selection_strategy"),
            "presentation_version": profile.get("presentation_version"),
            "redaction_policy_version": profile.get("redaction_policy_version"),
            "sizing_recovery": compact_fields(
                profile.get("sizing_recovery", {}), ("applied", "reason", "retries")
            ),
            "omissions": sanitize(profile.get("omissions", {}), depth=1),
        }
    if compact_result_review is not None:
        compact_result["review_summary"] = compact_result_review
    compact_result["analysis"] = compact_analysis
    reduced_report = {
        "schema": report.get("schema"),
        "tool_version": report.get("tool_version"),
        "generated_at": report.get("generated_at"),
        "result": compact_result,
    }
    details = {
        "findings": finding_counts,
        "coverage_limitations": limitation_counts,
        "coverage_gaps": gap_counts,
        "code_exposure": code_counts,
        "analysis_fingerprint": compact_analysis["analysis_fingerprint"],
    }
    if compact_result_review is not None:
        details["review_summary"] = compact_result_review
        details["freshness"] = bounded_string(review_summary.get("freshness", "unknown"), 64)
        details["presentation_complete"] = review_summary.get("presentation_complete") is True
    return reduced_report, details


def _encoded_summary(summary: dict[str, Any]) -> bytes:
    return json.dumps(summary, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _minimal_truncated_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded status record when evidence cannot fit the transport cap."""
    transport = summary.get("transport") if isinstance(summary.get("transport"), dict) else {}
    command = summary.get("command") if isinstance(summary.get("command"), list) else []
    return {
        "evidence_label": "UNTRUSTED OMASAFE EVIDENCE",
        "command": [bounded_string(item, 128) for item in command[:4]],
        "cli": bounded_string(summary.get("cli", ""), 128),
        "status": "truncated",
        "exit_code": summary.get("exit_code"),
        "transport": {
            "summary_max_bytes": SUMMARY_CAP,
            "summary_truncated": True,
            "summary_reduced": False,
            "stream_truncated": bool(transport.get("stream_truncated")),
            "timed_out": bool(transport.get("timed_out")),
        },
        "message": "structured summary exceeded cap",
    }


def _fit_summary_to_cap(summary: dict[str, Any]) -> dict[str, Any]:
    """Iteratively shed optional evidence, then fail closed with a tiny record."""
    budget = SUMMARY_CAP - 1  # the caller appends a newline
    if len(_encoded_summary(summary)) <= budget:
        return summary

    # A reduction can still be large when source-derived fields are all near
    # their individual bounds. Repeatedly halve retained arrays and remove
    # redundant aggregate detail until the serialized size is measured safe.
    for _ in range(12):
        if len(_encoded_summary(summary)) <= budget:
            return summary
        changed = False
        report = summary.get("report")
        result = report.get("result") if isinstance(report, dict) else None
        analysis = result.get("analysis") if isinstance(result, dict) else None
        if isinstance(analysis, dict):
            for field in ("findings", "coverage_gaps", "coverage_limitations"):
                values = analysis.get(field)
                if isinstance(values, list) and len(values) > 1:
                    kept = bounded_ordered_items(values, max(1, len(values) // 2))
                    analysis[field] = kept
                    details = summary.get("analysis_summary")
                    if isinstance(details, dict):
                        count = details.get(field)
                        if isinstance(count, dict):
                            total = _bounded_count(count.get("total"))
                            cli_emitted = _bounded_count(count.get("cli_emitted"))
                            count["emitted"] = len(kept)
                            if total is not None:
                                count["omitted"] = max(0, total - len(kept))
                            if cli_emitted is not None:
                                count["transport_emitted"] = len(kept)
                                count["transport_omitted"] = max(0, cli_emitted - len(kept))
                    changed = True
            for finding in analysis.get("findings", []):
                if isinstance(finding, dict):
                    for field in ("evidence_steps", "behavior_context", "presentation"):
                        if field in finding:
                            finding.pop(field, None)
                            changed = True
        payload = result.get("payload_inventory") if isinstance(result, dict) else None
        if isinstance(payload, dict):
            values = payload.get("code_exposure")
            if isinstance(values, list) and len(values) > 1:
                kept = bounded_ordered_items(values, max(1, len(values) // 2))
                payload["code_exposure"] = kept
                details = summary.get("analysis_summary")
                if isinstance(details, dict):
                    count = details.get("code_exposure")
                    if isinstance(count, dict):
                        total = _bounded_count(count.get("total"))
                        cli_emitted = _bounded_count(count.get("cli_emitted"))
                        count["emitted"] = len(kept)
                        if total is not None:
                            count["omitted"] = max(0, total - len(kept))
                        if cli_emitted is not None:
                            count["transport_emitted"] = len(kept)
                            count["transport_omitted"] = max(0, cli_emitted - len(kept))
                changed = True
        details = summary.get("analysis_summary")
        if isinstance(details, dict) and "review_summary" in details:
            details.pop("review_summary", None)
            changed = True
        if isinstance(result, dict) and "review_summary" in result:
            result.pop("review_summary", None)
            changed = True
        transport = summary.get("transport")
        if isinstance(transport, dict) and "summary_reduction" in transport:
            transport.pop("summary_reduction", None)
            changed = True
        if not changed:
            break

    return _minimal_truncated_summary(summary)


def make_summary(args: list[str], cli: str, timeout: float) -> dict[str, Any]:
    command, _ = command_parts(args)
    cap = SCAN_STREAM_CAP if command in {"scan", "scan-plugin"} else OTHER_STREAM_CAP
    safe_args = [bounded_string(item, ARGV_ITEM_CAP) for item in redact_args(args[:ARGV_COUNT_CAP])]
    if len(args) > ARGV_COUNT_CAP:
        safe_args.append("[argv items omitted]")
    summary: dict[str, Any] = {
        "evidence_label": "UNTRUSTED OMASAFE EVIDENCE",
        "command": safe_args,
        "cli": bounded_string(cli, ARGV_ITEM_CAP),
        "status": "error",
        "exit_code": None,
        "transport": {
            "max_stream_bytes": cap,
            "summary_max_bytes": SUMMARY_CAP,
            "timeout_seconds": timeout,
            "timed_out": False,
            "stream_truncated": False,
            "summary_truncated": False,
            "summary_reduced": False,
        },
    }
    parsed_report: dict[str, Any] | None = None

    try:
        proc = subprocess.Popen(
            [cli, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=(os.name == "posix"),
        )
    except (OSError, ValueError) as error:
        summary["error"] = bounded_string(f"could not execute omasafe-cli: {error}")
        summary = _fit_summary_to_cap(summary)
        assert len(_encoded_summary(summary)) + 1 <= SUMMARY_CAP
        return summary

    try:
        stdout, stderr, transport = capture(proc, cap, timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        kill_process(proc)
        summary["error"] = bounded_string(f"transport failure: {error}")
        transport = {"timed_out": False, "stream_truncated": False, "stdout_bytes": 0, "stderr_bytes": 0}
        stdout, stderr = b"", b""
    code = exit_code(proc)
    summary["exit_code"] = code
    summary["transport"].update(transport)

    if transport.get("timed_out"):
        summary["status"] = "timeout"
    elif transport.get("stream_truncated"):
        summary["status"] = "truncated"
    elif code == 130:
        summary["status"] = "interrupted"
    elif is_text_only(args):
        if code == 0:
            summary["status"] = "ok"
        elif code == 1 and stderr.lstrip().startswith(b"omasafe:"):
            summary["status"] = "text-error"
        elif code == 2:
            summary["status"] = "usage-error"
        else:
            summary["status"] = "error"
        summary["stdout"] = text_from_bytes(stdout)
        summary["stderr"] = text_from_bytes(stderr)
    elif has_json_format(args):
        try:
            parsed = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            summary["status"] = "unsupported" if code in {0, 3, 4} else "error"
            summary["error"] = bounded_string(f"invalid JSON report: {error}")
            summary["stderr"] = text_from_bytes(stderr)
        else:
            if isinstance(parsed, dict):
                parsed_report = parsed
            valid, validation_error = validate_report(parsed, args)
            if not valid:
                summary["status"] = "unsupported"
                summary["error"] = bounded_string(validation_error or "unsupported report")
                summary["stderr"] = text_from_bytes(stderr)
            elif code == 0:
                summary["status"] = "ok"
                summary["report"] = sanitize(parsed)
                if is_analyzer(args):
                    summary["analysis_summary"] = analysis_summary(parsed)
            elif code == 3 and command == "scan":
                summary["status"] = "actionable-report"
                summary["report"] = sanitize(parsed)
                summary["analysis_summary"] = analysis_summary(parsed)
            elif code == 4 and is_analyzer(args) and "--fail-on" in args:
                summary["status"] = "threshold-report"
                summary["report"] = sanitize(parsed)
                summary["analysis_summary"] = analysis_summary(parsed)
            elif code == 1:
                summary["status"] = "text-error"
                summary["stderr"] = text_from_bytes(stderr)
            else:
                summary["status"] = "error"
                summary["stderr"] = text_from_bytes(stderr)
            if "report" in summary and command == "posture":
                summary["posture_summary"] = posture_summary(parsed)
    else:
        summary["status"] = "error" if code not in {0, 2} else ("ok" if code == 0 else "usage-error")
        summary["stdout"] = text_from_bytes(stdout)
        summary["stderr"] = text_from_bytes(stderr)

    encoded = _encoded_summary(summary)
    if len(encoded) > SUMMARY_CAP - 1:
        summary["transport"]["summary_truncated"] = True
        reduced = reduce_analysis_report(parsed_report) if "report" in summary and parsed_report is not None else None
        if reduced is not None:
            reduced_report, details = reduced
            summary["report"] = reduced_report
            summary["analysis_summary"] = details
            summary["transport"]["summary_reduced"] = True
            summary["transport"]["summary_reduction"] = details
            summary["message"] = "structured report reduced to bounded finding and coverage evidence"
            summary["underlying_status"] = summary["status"]
            summary["status"] = "summary-reduced"
        else:
            summary["transport"]["summary_reduced"] = False
            if "stdout" in summary:
                summary["stdout"] = "[structured summary exceeded cap]"
            if "stderr" in summary:
                summary["stderr"] = "[structured summary exceeded cap]"
            summary["message"] = "structured summary exceeded cap"
            summary["status"] = "truncated"
    summary = _fit_summary_to_cap(summary)
    # Keep this assertion adjacent to the return so future changes cannot
    # accidentally emit an oversized JSON line after reduction.
    assert len(_encoded_summary(summary)) + 1 <= SUMMARY_CAP
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", default="omasafe-cli", help="path or name of the CLI")
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="place after --")
    options = parser.parse_args()
    args = options.command
    if args and args[0] == "--":
        args = args[1:]
    timeout = options.timeout
    if timeout is None:
        if is_marketplace_refresh(args):
            timeout = MARKETPLACE_REFRESH_TIMEOUT
        elif is_remote_candidate(args):
            timeout = REMOTE_TIMEOUT
        else:
            timeout = 30.0
    summary = make_summary(args, options.cli, max(0.1, timeout))
    encoded = _encoded_summary(summary).decode("ascii")
    sys.stdout.write(encoded + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
