"""Index explicitly supplied research reports without treating them as accepted evidence."""
import argparse
import hashlib
import json
from pathlib import Path


def candidate_records(value, location=""):
    """Retain reported tuning candidates with their original JSON location."""
    records = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{location}/{key}"
            if key == "candidates" and isinstance(child, list):
                records.extend({"location": f"{path}/{index}", "reported_candidate": candidate}
                               for index, candidate in enumerate(child))
            else:
                records.extend(candidate_records(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            records.extend(candidate_records(child, f"{location}/{index}"))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    paths = sorted(set(args.reports))
    runs = []
    for path in paths:
        raw = path.read_bytes()
        report = json.loads(raw)
        candidates = candidate_records(report)
        runs.append({
            "report": str(path), "report_sha256": hashlib.sha256(raw).hexdigest(),
            "reported_tuning_candidate_count": len(candidates),
            "reported_tuning_candidates": candidates,
            "approved_for_trading": False,
        })
    output = {
        "schema_version": 1,
        "scope": "Explicitly indexed available training and forecast evaluation reports",
        "limitations": [
            "A retrospective inventory, not a preregistered trial ledger",
            "Incomplete: additional diagnostic replays, overwritten attempts and manual choices may exist",
            "Repeated fits and inspected evaluation periods remain separate research attempts",
            "Candidate counts cover only explicitly recorded candidates arrays; not all fits or hypotheses",
            "Reported confidence intervals are not corrected for these repeated comparisons",
            "No indexed report establishes a locked untouched holdout or trading approval",
        ],
        "report_count": len(runs),
        "reported_tuning_candidate_count": sum(r["reported_tuning_candidate_count"] for r in runs),
        "runs": runs,
    }
    with args.output.open("x") as stream:
        stream.write(json.dumps(output, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
