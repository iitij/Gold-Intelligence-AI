"""Restore the captured Windows MT5 Python client from three local pinned archives."""

import argparse
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

INPUTS = {
    "python-embed.zip": "009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b",
    "wheels/numpy-1.26.4-cp311-cp311-win_amd64.whl":
        "cd25bcecc4974d09257ffcd1f098ee778f7834c3ad767fe5db785be9a4aa9cb2",
    "wheels/metatrader5-5.0.6231-cp311-cp311-win_amd64.whl":
        "1e0fb5e43437f426be3e5aef614f6798a918377db4cdb380593a66d1908f918d",
}


def stage(source, output):
    inputs = {}
    for name, expected in INPUTS.items():
        blob = (source / name).read_bytes()
        if hashlib.sha256(blob).hexdigest() != expected:
            raise ValueError(f"Captured archive fingerprint differs: {name}")
        inputs[name] = blob
    output.mkdir()
    for name, blob in inputs.items():
        target = output if name.endswith(".zip") else output / "Lib" / "site-packages"
        with ZipFile(io.BytesIO(blob)) as archive:
            archive.extractall(target)
    # Isolate imports from global packages and leave site startup hooks disabled.
    (output / "python311._pth").write_bytes(b"python311.zip\r\n.\r\nLib/site-packages\r\n")
    report = {"schema_version": 1, "platform": "win_amd64",
              "archive_sha256": INPUTS, "packages": {"python": "3.11.9", "numpy": "1.26.4",
                                                      "MetaTrader5": "5.0.6231"},
              "terminal_or_wine_installed": False, "runtime_execution_verified": False}
    (output / "stage.json").write_text(json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    stage(args.source, args.output)


if __name__ == "__main__":
    main()
