"""One-time exact-commit source freeze. Never refresh, overwrite or auto-sync."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"
DEST = VENDOR / "snapshots"
MANIFEST = VENDOR / "SNAPSHOT_MANIFEST.json"
MAX_SOURCE_SIZE = 120 * 1024 * 1024


def run(*argv: str, cwd: Path | None = None):
    return subprocess.check_output(
        argv, cwd=cwd, text=True, stderr=subprocess.PIPE
    ).strip()


def import_one(source: dict, stage: Path):
    repo, sha = source["repository"], source["commit"]
    with tempfile.TemporaryDirectory(prefix="gold-upstream-") as td:
        checkout = Path(td) / "checkout"
        run("git", "init", "-q", str(checkout))
        run("git", "remote", "add", "origin", source["url"] + ".git", cwd=checkout)
        run("git", "fetch", "--depth", "1", "--no-tags", "origin", sha, cwd=checkout)
        run("git", "checkout", "-q", "--detach", "FETCH_HEAD", cwd=checkout)
        got = run("git", "rev-parse", "HEAD", cwd=checkout)
        if got != sha:
            raise RuntimeError("SHA mismatch in " + repo)
        if not any((checkout / x).is_file()
                   for x in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")):
            raise RuntimeError("Missing top-level license for " + repo)
        dst = stage / repo.replace("/", "--")
        count, total = 0, 0
        digest = hashlib.sha256()
        for item in sorted(checkout.rglob("*")):
            rel = item.relative_to(checkout)
            if ".git" in rel.parts:
                continue
            if item.is_symlink():
                raise RuntimeError("Symlink requires review: " + str(rel))
            if not item.is_file():
                continue
            blob = item.read_bytes()
            total += len(blob)
            if total > MAX_SOURCE_SIZE:
                raise RuntimeError("Source too large; manual scoped import required")
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
            digest.update(rel.as_posix().encode() + b"\0" + hashlib.sha256(blob).digest())
            count += 1
        return {
            "repository": repo,
            "commit": got,
            "file_count": count,
            "digest_sha256": digest.hexdigest(),
            "license_status": source["license_status"],
            "upstream_updates_allowed": False,
        }


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--confirm", action="store_true")
    parser.add_argument("--include-optional", action="store_true")
    args = parser.parse_args()
    lock = json.loads((ROOT / "sources/sources.lock.json").read_text())
    modes = {"snapshot-approved"}
    if args.include_optional:
        modes.add("snapshot-optional")
    entries = [x for x in lock["sources"] if x["mode"] in modes]
    if any(x["license_status"] not in {"MIT", "Apache-2.0"} for x in entries):
        raise SystemExit("License review needed")
    if args.dry_run:
        for x in entries:
            print("WOULD FREEZE:", x["repository"], x["commit"])
        return
    if DEST.exists() or MANIFEST.exists():
        raise SystemExit("Already frozen; never overwrite or sync upstream")
    VENDOR.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".gold-freeze-", dir=VENDOR))
    try:
        imported = [import_one(x, stage) for x in entries]
        payload = {"format_version": 1, "sealed": True,
                   "upstream_updates_allowed": False, "snapshots": imported}
        tmp = VENDOR / ".SNAPSHOT_MANIFEST.json.tmp"
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        stage.rename(DEST)
        tmp.rename(MANIFEST)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print("Full source snapshots sealed; run security and license audit before use")


if __name__ == "__main__":
    main()