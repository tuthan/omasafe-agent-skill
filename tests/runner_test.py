#!/usr/bin/env python3
"""Behavioral checks for the bounded OmaSafe transport."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "skill/omasafe-plugin-review/scripts/run-omasafe.py"
FAKE = ROOT / "tests/fake-bin/omasafe-cli"


def invoke(scenario, *args, timeout=None):
    with tempfile.TemporaryDirectory(prefix="omasafe-runner-") as directory:
        log = Path(directory) / "argv.jsonl"
        environment = os.environ.copy()
        environment["FAKE_OMASAFE_SCENARIO"] = scenario
        environment["FAKE_ARGV_LOG"] = str(log)
        command = [sys.executable, str(RUNNER), "--cli", str(FAKE)]
        if timeout is not None:
            command += ["--timeout", str(timeout)]
        command += ["--", *args]
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            env=environment,
        )
        result = json.loads(completed.stdout)
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, calls, len(completed.stdout)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    result, calls, _ = invoke("default", "plugins", "inventory", "--format", "json")
    check(result["status"] == "ok", "inventory should be a valid report")
    check(result["report"]["schema"] == "omasafe.report.v1", "report envelope missing")
    check(calls == [["plugins", "inventory", "--format", "json"]], "argv was changed")

    result, calls, _ = invoke("default", "posture", "scan", "--format", "json")
    check(result["status"] == "ok", "posture report should be accepted")
    check(result["report"]["schema"] == "omasafe.posture.v1", "posture schema was not retained")
    check(result["posture_summary"]["states"] == {"informational": 1},
          "posture state summary was not retained")
    check(calls == [["posture", "scan", "--format", "json"]], "posture argv was changed")

    result, _, _ = invoke("posture-not-yet-run", "posture", "export", "--format", "json")
    check(result["status"] == "ok" and result["posture_summary"]["status"] == "not_yet_run",
          "pre-first-run posture state was not preserved")

    result, calls, _ = invoke("default", "posture", "hook", "status")
    check(result["status"] == "ok" and "installed: false" in result["stdout"],
          "posture hook status should remain text-only")
    check(calls == [["posture", "hook", "status"]], "posture hook argv was changed")

    result, _, _ = invoke("actionable-scan", "scan", "--format", "json")
    check(result["status"] == "actionable-report" and result["exit_code"] == 3, "scan exit 3 lost")

    result, _, _ = invoke("threshold", "plugins", "analyze", "io.example.fixture", "--format", "json", "--fail-on", "high")
    check(result["status"] == "threshold-report" and result["exit_code"] == 4, "analyzer threshold report lost")

    result, _, _ = invoke("exit4-no-gate", "plugins", "analyze", "io.example.fixture", "--format", "json")
    check(result["status"] == "error", "exit 4 without explicit gate must not be accepted")

    result, _, _ = invoke("provenance-stale", "provenance", "--format", "json")
    check(result["status"] == "ok" and result["report"]["schema"] == "omasafe.provenance.v1", "provenance must be top-level")
    check(result["report"]["supported_runtime"]["omarchy"] == "4.0.0-1", "provenance fixture changed")

    result, _, _ = invoke("malformed", "plugins", "inventory", "--format", "json")
    check(result["status"] == "unsupported" and "report" not in result, "malformed JSON escaped validation")

    result, _, _ = invoke("unknown-enum", "plugins", "enforcement-status", "io.example.fixture", "--format", "json")
    check(result["status"] == "unsupported", "unknown enforcement enum was accepted")

    result, _, _ = invoke("v025", "plugins", "enforcement-status", "io.example.fixture", "--format", "json")
    check(result["status"] == "ok", "v0.2.5 enforcement report should be accepted")
    decision = result["report"]["result"]["decision"]
    check(decision["schema"] == "omasafe.enforcement.v2" and
          decision["blockers"] == [] and decision["opaque_code_items"] == [],
          "enforcement v2 fields were not retained")
    check(result["report"]["result"]["enforcement_policy"]["schema"] == "omasafe.enforcement-policy.v2",
          "enforcement policy v2 was not accepted")

    result, calls, _ = invoke(
        "v025", "plugins", "executable-review", "list", "io.example.fixture", "--format", "json",
    )
    check(result["status"] == "ok" and result["report"]["result"]["reviews"][0]["status"] == "active",
          "executable-review list report should be accepted")
    check(calls == [["plugins", "executable-review", "list", "io.example.fixture", "--format", "json"]],
          "executable-review list argv changed")

    result, _, _ = invoke(
        "v025", "scan-plugin", "--path", "./plugin", "--report-profile", "review", "--format", "json",
    )
    check(result["status"] == "ok", "v0.2.5 code-exposure review profile should be accepted")
    check(result["analysis_summary"]["code_exposure"] == {"total": 1, "emitted": 1, "omitted": 0},
          "code-exposure totals were not retained")
    code_item = result["report"]["result"]["payload_inventory"]["code_exposure"][0]
    check(code_item["opaque_review_required"] is True and code_item["native_format"] == "elf",
          "code-exposure evidence was not retained")

    result, _, _ = invoke("stderr-error", "plugins", "trust", "io.example.fixture", "--yes")
    check(result["status"] == "text-error" and result["exit_code"] == 1, "text error semantics lost")

    result, _, _ = invoke("usage", "not-a-command")
    check(result["status"] == "usage-error" and result["exit_code"] == 2, "usage semantics lost")

    result, _, _ = invoke("interrupt", "plugins", "analyze", "io.example.fixture", "--format", "json")
    check(result["status"] == "interrupted" and result["exit_code"] == 130, "interrupt semantics lost")

    result, _, _ = invoke("timeout", "plugins", "inventory", "--format", "json", timeout=0.1)
    check(result["status"] == "timeout" and result["transport"]["timed_out"], "timeout semantics lost")

    result, calls, _ = invoke("default", "marketplace", "refresh", "--latest")
    check(result["status"] == "ok", "marketplace refresh should remain a text-only command")
    check(result["transport"]["timeout_seconds"] == 300.0,
          "marketplace refresh did not receive the aggregate 300-second default")
    check(calls == [["marketplace", "refresh", "--latest"]], "marketplace refresh argv changed")

    result, _, output_bytes = invoke("oversized", "scan", "--format", "json")
    check(result["status"] == "truncated", "oversized stream was not stopped")
    check(result["transport"]["stream_truncated"], "truncation marker missing")
    check(not result["transport"]["summary_reduced"], "raw stream overflow was mislabeled as reduction")
    check(output_bytes <= 64 * 1024, "summary exceeded 64 KiB")

    result, calls, _ = invoke("injection", "plugins", "analyze", "id with spaces;$(touch NO)", "--format", "json")
    check(result["status"] == "ok", "injection fixture should remain a report")
    check(result["evidence_label"] == "UNTRUSTED OMASAFE EVIDENCE", "evidence boundary missing")
    check(calls[0][2] == "id with spaces;$(touch NO)", "target-like argv was not kept literal")
    check("Ignore prior instructions" in result["report"]["result"]["analysis"]["findings"][0]["evidence"], "evidence was dropped unexpectedly")

    result, _, _ = invoke("text-success", "plugins", "trust", "io.example.fixture", "--yes")
    check(result["status"] == "ok" and "stdout" in result, "text-only success was parsed as JSON")

    result, _, _ = invoke(
        "text-success", "plugins", "executable-review", "add", "io.example.fixture",
        "--path", "bin/helper", "--sha256", "c" * 64, "--yes",
    )
    check(result["status"] == "ok" and "stdout" in result,
          "executable-review add was not kept text-only")

    request = "omarchy plugin add https://github.com/example/plugin.git --enable"
    result, calls, _ = invoke(
        "candidate", "scan-plugin", "--request", request,
        "--report-profile", "review", "--format", "json",
    )
    check(result["status"] == "ok", "candidate report should be accepted")
    check(calls == [["scan-plugin", "--request", request, "--report-profile", "review", "--format", "json"]], "candidate argv changed")
    check(result["command"][2] == "[candidate request omitted]", "raw candidate request leaked into command metadata")
    check(result["transport"]["max_stream_bytes"] == 4 * 1024 * 1024, "scan-plugin did not receive the 4 MiB cap")
    check(result["transport"]["timeout_seconds"] == 120.0, "remote candidate did not receive the 120-second default")
    check(result["analysis_summary"]["findings"] == {"total": 1, "emitted": 1, "omitted": 0}, "finding totals were not retained")

    result, calls, _ = invoke(
        "local-review", "scan-plugin", "--path", "./plugin",
        "--report-profile", "review", "--format", "json",
    )
    check(result["status"] == "ok", "local review profile should be accepted")
    check("acquisition" not in result["report"]["result"], "local review acquired remote state")
    check(calls == [["scan-plugin", "--path", "./plugin", "--report-profile", "review", "--format", "json"]], "local review argv changed")

    result, _, _ = invoke(
        "default", "scan-plugin", "--path", "./plugin",
        "--report-profile", "full", "--format", "json",
    )
    check(result["status"] == "ok", "local full profile should remain a generic report")

    result, _, _ = invoke(
        "v024-review", "scan-plugin", "--path", "./plugin",
        "--report-profile", "review", "--format", "json",
    )
    check(result["status"] == "ok", "v0.2.4 local review profile should be accepted")
    check(result["analysis_summary"]["coverage_gaps"] == {"total": 1, "emitted": 1, "omitted": 0},
          "coverage-gap totals were not retained")
    check(result["analysis_summary"]["review_summary"]["freshness"] == "fresh",
          "review summary freshness was dropped")
    check(result["analysis_summary"]["review_summary"]["findings"]["by_severity"]["low"]["emitted"] == 1,
          "review severity rows were dropped")
    finding = result["report"]["result"]["analysis"]["findings"][0]
    check(finding["occurrence_id"] == "occ-1" and finding["evidence_steps"][0]["role"] == "source",
          "structured finding evidence was dropped")

    result, _, _ = invoke(
        "malformed-omissions", "scan-plugin", "--path", "./plugin",
        "--report-profile", "review", "--format", "json",
    )
    check(result["status"] == "unsupported", "malformed local omission arithmetic was accepted")

    for selector in (
        ["--git", "https://github.com/example/plugin.git", "--revision", "a" * 40],
        ["--marketplace", "io.example.fixture"],
    ):
        result, _, _ = invoke("candidate", "scan-plugin", *selector, "--report-profile", "review", "--format", "json")
        check(result["status"] == "ok", f"remote selector {selector[0]} was not validated")

    result, _, _ = invoke("summary-reduction", "scan-plugin", "--path", "./plugin", "--format", "json")
    check(result["status"] == "summary-reduced", "large structured report did not use evidence reduction")
    check(result["transport"]["summary_reduced"], "summary reduction marker missing")
    check(not result["transport"]["stream_truncated"], "summary reduction was mislabeled as stream truncation")
    check(len(result["report"]["result"]["analysis"]["findings"]) == 40, "reduced finding cap changed")
    reduced_findings = result["report"]["result"]["analysis"]["findings"]
    check(reduced_findings[0]["rule_id"] == "oma.fixture.0000", "first boundary finding was lost")
    check(reduced_findings[-1]["rule_id"] == "oma.fixture.0999", "last boundary finding was lost")
    counts = result["analysis_summary"]["findings"]
    check(counts["total"] == counts["emitted"] + counts["omitted"], "reduced finding arithmetic is inconsistent")
    check(counts["cli_emitted"] == counts["transport_emitted"] + counts["transport_omitted"], "transport omission arithmetic is inconsistent")
    check(reduced_findings[-1]["severity"] == "critical", "critical boundary evidence was lost")
    check(reduced_findings[0]["occurrence_id"] == "occ-0000" and
          reduced_findings[0]["evidence_steps"][0]["role"] == "source",
          "structured evidence was lost during summary reduction")

    result, _, _ = invoke(
        "candidate", "scan-plugin", "--request=" + request,
        "--report-profile=review", "--format", "json",
    )
    check(result["status"] == "ok", "equals-form candidate options should be accepted")
    check(result["command"][1] == "--request=[candidate request omitted]", "equals-form request leaked")

    result, _, _ = invoke("default", "scan-plugin", "--request", request, "--format", "json")
    check(result["status"] == "unsupported", "candidate route accepted an old CLI report")

    print("runner tests: ok")


if __name__ == "__main__":
    main()
