"""Restore a pinned Headway evidence archive privately and repeat its reconciliation."""

import argparse
import hashlib
import json
import tarfile
from contextlib import chdir
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from archive_headway_tick_evidence import MANIFEST, sha
from reconcile_headway_attempts import native_bound, previous_attempts, reconcile


def relative_name(name):
    path = PurePosixPath(name)
    if (path.is_absolute() or not path.parts or ".." in path.parts or "\\" in name
            or name != path.as_posix()):
        raise ValueError("Archive evidence paths must be canonical relative names")
    return name


def unpack(bundle, restore):
    members = {}
    for member in bundle:
        name = relative_name(member.name)
        if name in members or member.type not in {tarfile.REGTYPE, tarfile.DIRTYPE}:
            raise ValueError("Unexpected or duplicate archive member")
        members[name] = member
    if MANIFEST not in members or not members[MANIFEST].isfile():
        raise ValueError("Missing evidence manifest")
    manifest = json.load(bundle.extractfile(members[MANIFEST]))
    if manifest["schema_version"] != 1:
        raise ValueError("Unsupported evidence archive manifest")
    files = manifest["files_sha256"]
    batches = set(manifest["batch_directories"])
    if (MANIFEST in files or set(files) & batches
            or set(members) != {MANIFEST, *files, *batches}):
        raise ValueError("Archive members disagree with manifest")
    for name in sorted(batches):
        if not members[name].isdir():
            raise ValueError("Expected a batch directory")
        (restore / name).mkdir(parents=True, exist_ok=True)
    for name, digest in files.items():
        if not members[name].isfile():
            raise ValueError("Expected a regular evidence file")
        raw = bundle.extractfile(members[name]).read()
        if sha(raw) != digest:
            raise ValueError(f"Restored evidence fingerprint differs: {name}")
        path = restore / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    return manifest


def audit_restored(manifest, anchors):
    files = manifest["files_sha256"]
    report_name = relative_name(manifest["reconciliation"])
    if files.get(report_name) != manifest["reconciliation_sha256"]:
        raise ValueError("Reconciliation fingerprint disagrees with manifest")
    saved = json.loads(Path(report_name).read_bytes())
    if saved["all_requests_reconciled"] is not True:
        raise ValueError("Expected a fully accounted reconciliation")
    for source in saved["attempts"]:
        root = relative_name(source["attempt"])
        if f"{root}/batches" not in manifest["batch_directories"] or f"{root}/export.log" not in files:
            raise ValueError("Reconciliation references evidence outside the manifest")
    for anchor in anchors:
        name = relative_name(anchor.as_posix())
        if name not in files:
            raise ValueError("Clock receipt must exist in this archive")
        for filename, digest in json.loads(anchor.read_bytes())["file_sha256"].items():
            if files.get(relative_name(filename)) != digest:
                raise ValueError("Clock evidence differs from the archive manifest")
    attempts, guarded = previous_attempts(saved, anchors)
    start = native_bound(saved["windows"][0]["native_start"])
    end = native_bound(saved["windows"][-1]["native_end_exclusive"])
    rebuilt = reconcile(start, end, attempts, guarded=guarded)
    if rebuilt != {key: value for key, value in saved.items() if key != "previous_report_sha256"}:
        raise ValueError("Restored reconciliation differs from the archived report")
    return {"reconciliation_sha256": manifest["reconciliation_sha256"],
            "restored_files_verified": len(files), "rebuilt_attempts": len(attempts),
            "restored_window_status_counts": rebuilt["window_status_counts"]}


def verify(bundle_path, expected, anchors):
    with bundle_path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError("Archive fingerprint differs")
        stream.seek(0)
        with TemporaryDirectory(prefix="headway-restore-") as tmp:
            with tarfile.open(fileobj=stream, mode="r:gz") as bundle:
                manifest = unpack(bundle, Path(tmp))
            with chdir(tmp):
                result = audit_restored(manifest, anchors)
    return {"schema_version": 1, "archive_sha256": expected, **result,
            "off_host_backup_verified": False, "utc_mapping_verified": False, "holdout_scored": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("sha256")
    parser.add_argument("output", type=Path)
    parser.add_argument("--clock-receipt", type=Path, action="append", default=[])
    args = parser.parse_args()
    result = verify(args.archive, args.sha256, args.clock_receipt)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(f"Verified and re-audited {result['restored_files_verified']} evidence files")


if __name__ == "__main__":
    main()
