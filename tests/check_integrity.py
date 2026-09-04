#!/usr/bin/env python3
"""Verify the release integrity manifest and its deterministic contents."""

from hashlib import sha256
from pathlib import Path
import subprocess
import sys


root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]).resolve()
manifest = root / "SHA256SUMS"
if not manifest.is_file():
    raise SystemExit("missing SHA256SUMS")

manifest_before = manifest.read_bytes()
entries = {}
for raw in manifest_before.decode("utf-8").splitlines():
    if not raw or raw.startswith("#"):
        continue
    digest, relative = raw.split("  ", 1)
    if relative in entries:
        raise SystemExit(f"duplicate manifest path: {relative}")
    path = root / relative
    if not path.is_file():
        raise SystemExit(f"manifest path is missing: {relative}")
    actual = sha256(path.read_bytes()).hexdigest()
    if actual != digest:
        raise SystemExit(f"digest mismatch: {relative}")
    entries[relative] = digest

subprocess.run([sys.executable, str(root / "tests/generate_integrity.py"), str(root)], check=True, capture_output=True)
if manifest_before != manifest.read_bytes():
    raise SystemExit("integrity manifest generation was not deterministic")
if not entries:
    raise SystemExit("empty integrity manifest")
print(f"integrity: ok ({len(entries)} files)")
