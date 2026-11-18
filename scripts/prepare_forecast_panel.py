"""Create contiguous M15 forecast panels with explicit temporal splits."""
import argparse
import json
from pathlib import Path

import pandas as pd

from goldintel.data.mt5_csv import validate_mt5_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("feeds", nargs="+", type=Path)
    args = parser.parse_args()
    args.output.mkdir()
    manifest = {}
    for path in args.feeds:
        audit = validate_mt5_csv(path, expected_symbol="XAUUSD")
        bars = pd.read_csv(path)
        time = pd.to_datetime(bars.server_time, format="%Y.%m.%d %H:%M:%S") + pd.Timedelta(minutes=15)
        split = pd.Series("test", index=bars.index)
        split.loc[time < pd.Timestamp("2026-04-01")] = "validation"
        split.loc[time < pd.Timestamp("2026-01-01")] = "train"
        segment = (~time.diff().eq(pd.Timedelta(minutes=15)) | split.ne(split.shift())).cumsum()
        frame = pd.DataFrame({
            "unique_id": path.stem + "-" + segment.astype(str),
            "ds": time, "y": bars.close, "split": split,
        })
        # 64 completed context bars and 16 future bars fit in each retained series.
        frame = frame.loc[frame.groupby("unique_id").y.transform("size") >= 80]
        for _, group in frame.groupby("unique_id"):
            assert group.ds.diff().dropna().eq(pd.Timedelta(minutes=15)).all()
            assert group.split.nunique() == 1
        frame.to_csv(args.output / f"{path.stem}.csv", index=False)
        manifest[path.name] = {
            "source_sha256": audit.source_sha256,
            "rows": frame.groupby("split").size().to_dict(),
            "segments": frame.groupby("split").unique_id.nunique().to_dict(),
        }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
