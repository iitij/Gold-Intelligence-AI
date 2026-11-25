"""Merge compatible native-time broker bar exports and reject conflicting overlap."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd

from goldintel.data.mt5_csv import validate_mt5_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("extension", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source_reports = [validate_mt5_csv(p, expected_symbol="XAUUSD")
                      for p in (args.original, args.extension)]
    original, extension = (pd.read_csv(p) for p in (args.original, args.extension))
    overlap = original.merge(extension, on="server_time", suffixes=("_old", "_new"),
                             validate="one_to_one")
    for column in original.columns.drop("server_time"):
        if not overlap[column + "_old"].eq(overlap[column + "_new"]).all():
            raise ValueError(f"Conflicting overlap in {column}")
    merged = pd.concat([original, extension]).drop_duplicates("server_time").sort_values("server_time")
    with NamedTemporaryFile(mode="w", dir=args.output.parent, delete=False) as stream:
        temporary = Path(stream.name)
        merged.to_csv(stream, index=False)
    try:
        audit = validate_mt5_csv(temporary, expected_symbol="XAUUSD")
        os.link(temporary, args.output)
    finally:
        temporary.unlink()
    manifest = {
        "chronology": "native broker time, historical UTC mapping unresolved",
        "source_sha256": [r.source_sha256 for r in source_reports],
        "rows": len(merged), "overlap_rows": len(overlap),
        "added_rows": len(merged) - len(original),
        "output_sha256": audit.source_sha256,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    with args.output.with_suffix(".manifest.json").open("x") as stream:
        json.dump(manifest, stream, indent=2)


if __name__ == "__main__":
    main()
