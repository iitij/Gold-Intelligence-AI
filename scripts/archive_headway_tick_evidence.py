"""Create a local, manifest-verified archive of reconciled Headway quote evidence."""

import argparse
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path
from tempfile import NamedTemporaryFile

from reconcile_headway_attempts import native_bound, previous_attempts, reconcile

MANIFEST = "headway-evidence-manifest.json"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def archive(report_path, expected, anchors, output):
    report_bytes = report_path.read_bytes()
    if sha(report_bytes) != expected:
        raise ValueError("Reconciliation report fingerprint differs")
    report = json.loads(report_bytes)
    if not report["all_requests_reconciled"]:
        raise ValueError("Only an accounted request range may be archived")
    windows = report["windows"]
    attempts, guarded = previous_attempts(report, anchors)
    rebuilt = reconcile(native_bound(windows[0]["native_start"]),
                        native_bound(windows[-1]["native_end_exclusive"]), attempts, guarded=guarded)
    if rebuilt != {key: value for key, value in report.items() if key != "previous_report_sha256"}:
        raise ValueError("The source evidence no longer matches the reconciliation")
    root_dir = Path.cwd().resolve()
    tree = report_path.parent.parent.resolve()
    files = {}

    def include(path, digest):
        absolute = path.absolute()
        if (path.is_absolute() or absolute != absolute.resolve() or not absolute.is_relative_to(tree)
                or not absolute.is_relative_to(root_dir) or not absolute.is_file()):
            raise ValueError("Use relative paths to regular files inside the local acquisition tree")
        rel = absolute.relative_to(root_dir).as_posix()
        if rel in files and files[rel] != digest:
            raise ValueError(f"Conflicting evidence fingerprints: {rel}")
        files[rel] = digest

    include(report_path, expected)
    for source in report["attempts"]:
        path = Path(source["attempt"])
        include(path / "export.log", source["export_log_sha256"])
        if "closed_request_sha256" in source:
            include(path / "closed-request.json", source["closed_request_sha256"])
    for window in windows:
        for row in window["observations"]:
            if row.get("file"):
                path = Path(report["attempts"][row["attempt_index"]]["attempt"])
                include(path / "batches" / row["file"], row["sha256"])
    for anchor in anchors:
        raw = anchor.read_bytes()
        include(anchor, sha(raw))
        for filename, digest in json.loads(raw)["file_sha256"].items():
            path = Path(filename)
            if not path.absolute().is_relative_to(anchor.parent.absolute()):
                raise ValueError("Clock evidence must be inside the receipt directory")
            include(path, digest)

    manifest = {"schema_version": 1, "reconciliation": report_path.as_posix(),
                "reconciliation_sha256": expected, "files_sha256": dict(sorted(files.items()))}
    manifest["batch_directories"] = sorted(
        (path.absolute() / "batches").relative_to(root_dir).as_posix() for path, _, _ in attempts
    )
    if output.exists():
        raise FileExistsError(output)
    with NamedTemporaryFile(dir=output.parent) as stream:
        with tarfile.open(fileobj=stream, mode="w:gz") as bundle:
            def add(name, raw):
                item = tarfile.TarInfo(name)
                item.size, item.mode = len(raw), 0o600
                bundle.addfile(item, io.BytesIO(raw))

            for directory in manifest["batch_directories"]:
                item = tarfile.TarInfo(directory)
                item.type, item.mode = tarfile.DIRTYPE, 0o700
                bundle.addfile(item)
            for path, digest in manifest["files_sha256"].items():
                raw = Path(path).read_bytes()
                if sha(raw) != digest:
                    raise ValueError(f"Evidence changed during archive: {path}")
                add(path, raw)
            add(MANIFEST, (json.dumps(manifest, indent=2) + "\n").encode())
        stream.flush()
        os.link(stream.name, output)
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("sha256")
    parser.add_argument("output", type=Path)
    parser.add_argument("--clock-receipt", type=Path, action="append", default=[])
    args = parser.parse_args()
    print(f"Archived {archive(args.report, args.sha256, args.clock_receipt, args.output)} evidence files")


if __name__ == "__main__":
    main()
