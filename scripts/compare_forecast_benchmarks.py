"""Select a forecaster by validation MAE on matched historical panels."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    paths = {
        "NHITS-200": Path("artifacts/nhits-20261117/report.json"),
        "NHITS-500": Path("artifacts/nhits-20261118-500/report.json"),
        "Chronos-2": Path("artifacts/chronos-20261118/report.json"),
    }
    reports = {name: json.loads(path.read_text()) for name, path in paths.items()}
    output = {"selection_metric": "validation price MAE", "feeds": {},
              "limitations": ["Historical dates previously inspected",
                              "Foundation pretraining overlap unverified",
                              "Metrics exclude execution costs"]}
    for feed in reports["NHITS-200"]["feeds"]:
        scores = {}
        baseline = reports["NHITS-200"]["feeds"][feed]
        for name, report in reports.items():
            result = report["feeds"][feed]
            for split in ("validation", "test"):
                if result[split]["rows"] != baseline[split]["rows"]:
                    raise ValueError("Evaluation row counts differ")
                if abs(result[split]["persistence_mae_price"] -
                       baseline[split]["persistence_mae_price"]) > 1e-8:
                    raise ValueError("Persistence outcomes differ between reports")
            scores[name] = {split: result[split]["mae_price"] for split in ("validation", "test")}
        scores["persistence"] = {
            split: baseline[split]["persistence_mae_price"] for split in ("validation", "test")
        }
        selected = min(scores, key=lambda name: scores[name]["validation"])
        output["feeds"][feed] = {"candidates": scores, "selected": selected,
                                 "selected_test_mae": scores[selected]["test"]}
    with args.output.open("x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
