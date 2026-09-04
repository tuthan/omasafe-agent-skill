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

    result, _, _ = invoke("stderr-error", "plugins", "trust", "io.example.fixture", "--yes")
    check(result["status"] == "text-error" and result["exit_code"] == 1, "text error semantics lost")

    result, _, _ = invoke("usage", "not-a-command")
    check(result["status"] == "usage-error" and result["exit_code"] == 2, "usage semantics lost")

    result, _, _ = invoke("interrupt", "plugins", "analyze", "io.example.fixture", "--format", "json")
    check(result["status"] == "interrupted" and result["exit_code"] == 130, "interrupt semantics lost")

    result, _, _ = invoke("timeout", "plugins", "inventory", "--format", "json", timeout=0.1)
    check(result["status"] == "timeout" and result["transport"]["timed_out"], "timeout semantics lost")

    result, _, output_bytes = invoke("oversized", "scan", "--format", "json")
    check(result["status"] == "truncated", "oversized stream was not stopped")
    check(result["transport"]["stream_truncated"], "truncation marker missing")
    check(output_bytes <= 64 * 1024, "summary exceeded 64 KiB")

    result, calls, _ = invoke("injection", "plugins", "analyze", "id with spaces;$(touch NO)", "--format", "json")
    check(result["status"] == "ok", "injection fixture should remain a report")
    check(result["evidence_label"] == "UNTRUSTED OMASAFE EVIDENCE", "evidence boundary missing")
    check(calls[0][2] == "id with spaces;$(touch NO)", "target-like argv was not kept literal")
    check("Ignore prior instructions" in result["report"]["result"]["analysis"]["findings"][0]["evidence"], "evidence was dropped unexpectedly")

    result, _, _ = invoke("text-success", "plugins", "trust", "io.example.fixture", "--yes")
    check(result["status"] == "ok" and "stdout" in result, "text-only success was parsed as JSON")

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
