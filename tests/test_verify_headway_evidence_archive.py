"""Restore must independently verify the manifest before rebuilding data evidence."""

import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path


def test_matching_archive_fingerprint_does_not_bypass_member_verification(tmp_path):
    bundle = tmp_path / "evidence.tar.gz"
    output = tmp_path / "result.json"
    evidence = "acquisition/attempt/export.log"
    original = hashlib.sha256(b"original").hexdigest()
    manifest = {"schema_version": 1, "files_sha256": {evidence: original}, "batch_directories": []}
    with tarfile.open(bundle, "w:gz") as tar:
        for name, raw in ((evidence, b"modified"), ("headway-evidence-manifest.json", json.dumps(manifest).encode())):
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            tar.addfile(member, io.BytesIO(raw))
    sha = hashlib.sha256(bundle.read_bytes()).hexdigest()
    script = Path(__file__).resolve().parents[1] / "scripts/verify_headway_evidence_archive.py"
    result = subprocess.run([sys.executable, str(script), str(bundle), sha, str(output)],
                            capture_output=True, text=True, check=False)
    assert result.returncode != 0 and "Restored evidence fingerprint differs" in result.stderr
    assert not output.exists()
