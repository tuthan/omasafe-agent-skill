#!/usr/bin/env python3
"""Check that the disposable fixture corpus pins every supported schema name."""

import json
from pathlib import Path


root = Path(__file__).resolve().parents[1]
samples = json.loads((root / "tests/fixtures/schema-samples.json").read_text(encoding="utf-8"))
expected = {
    "omasafe.report.v1",
    "omasafe.acquisition.v1",
    "omasafe.provenance.v1",
    "omasafe.analysis.v1",
    "omasafe.enforcement.v1",
    "omasafe.enforcement-policy.v1",
    "omasafe.enforcement-summary.v1",
    "omasafe.override.v1",
    "omasafe.enforcement-audit.v1",
    "omasafe.schedule.v1",
}
actual = {sample["schema"] for sample in samples.values()}
if actual != expected:
    raise SystemExit(f"schema fixture mismatch: {sorted(actual)}")
print("fixture schemas: ok")
