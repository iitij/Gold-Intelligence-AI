"""ONE-TIME archive of small review-only GitHub sources at exact approved SHAs.

WARNING: Archived code is untrusted. This script copies bytes only: never imports,
builds, or runs remote modules. It refuses to replace previous archives.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "sources/research_candidates_2026_11_08.lock.json"
OUT = ROOT / "vendor/research_refs"
MANIFEST = ROOT / "vendor/RESEARCH_REFS_MANIFEST.json"
MAX_BYTES = 2 * 1024 * 1024
PIN = re.compile(r"^[0-9a-f]{40}$")
SENSITIVE = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"ghp_[A-Za-z0-9]{36}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{40,}"),
]


def git(*cmd: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(
        ["git", *cmd], cwd=cwd, text=True, stderr=subprocess.PIPE
    ).strip()


def take_snapshot(record: dict, target: Path) -> dict:
    repo, sha = record["repository"], record["commit"]
    if not PIN.fullmatch(sha):
        raise ValueError("Repository not pinned to immutable SHA")
    if record["license"] not in {"MIT", "BSD-3-Clause"}:
        raise ValueError("No reviewed permissive license")
    if record["decision"] != "one-time-offline-review":
        raise ValueError("Code archive requires explicit review-only decision")
    with tempfile.TemporaryDirectory(prefix="gold-research-fetch-") as temp:
        checkout = Path(temp) / "src"
        git("init", "-q", str(checkout))
        git("remote", "add", "origin", "https://github.com/" + repo + ".git", cwd=checkout)
        git("fetch", "--depth", "1", "--no-tags", "origin", sha, cwd=checkout)
        git("checkout", "-q", "--detach", "FETCH_HEAD", cwd=checkout)
        if git("rev-parse", "HEAD", cwd=checkout) != sha:
            raise ValueError("Pinned Git SHA mismatch")
        if not any((checkout / x).is_file() for x in ("LICENSE", "LICENSE.txt", "LICENSE.md")):
            raise ValueError("Required license file not present")
        files = git("ls-files", "-z", cwd=checkout).split("\0")
        total = 0
        digest = hashlib.sha256()
        count = 0
        destination = target / repo.replace("/", "--")
        for rel in sorted(filter(None, files)):
            source = checkout / rel
            if source.is_symlink() or not source.is_file():
                raise ValueError("Symlink/non-file rejected: " + rel)
            if Path(rel).name.startswith(".env") and not Path(rel).name.endswith(".example"):
                raise ValueError("Potential secret config: " + rel)
            blob = source.read_bytes()
            if any(pat.search(blob) for pat in SENSITIVE):
                raise ValueError("Potential secret material: " + rel)
            total += len(blob)
            if total > MAX_BYTES:
                raise ValueError("Too large for small offline reference snapshot")
            dest = destination / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            digest.update(rel.encode("utf-8") + b"\0" + hashlib.sha256(blob).digest())
            count += 1
        return {
            "repository": repo,
            "commit": sha,
            "license": record["license"],
            "file_count": count,
            "total_bytes": total,
            "digest_sha256": digest.hexdigest(),
            "archive_only": True,
            "runtime_approved": False,
            "upstream_sync_allowed": False,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    targets = [x for x in lock["candidates"]
               if x["decision"] == "one-time-offline-review"]
    if len(targets) != 2:
        raise SystemExit("Expected exactly two reviewed reference-only repositories")
    if OUT.exists() or MANIFEST.exists():
        raise SystemExit("Research references already archived; never overwrite/sync")
    if not args.confirm:
        for x in targets:
            print("REVIEW SNAPSHOT (dry-run):", x["repository"], x["commit"])
        return
    with tempfile.TemporaryDirectory(prefix=".research-freeze-", dir=ROOT / "vendor") as td:
        stage = Path(td)
        snapshots = [take_snapshot(source, stage) for source in targets]
        manifest = {
            "schema_version": 1,
            "sealed": True,
            "policy": "offline-reference-only-no-execution-no-upstream-sync",
            "snapshots": snapshots,
        }
        stage.rename(OUT)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Archived", sum(s["file_count"] for s in snapshots),
          "untrusted reference files; no code was executed")


if __name__ == "__main__":
    main()
