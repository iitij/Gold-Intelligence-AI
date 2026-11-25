"""Exercise the local read-only gold tool contract at an operator-provided UTC instant."""

import argparse
import hashlib
import json
import re
from pathlib import Path

from goldintel.agents.tools import GoldTools, ToolEvidence, read_verified_record, utc
from goldintel.data.snapshot import load_market_snapshot

REGISTRY = Path(__file__).resolve().parents[1] / "docs/05-STRATEGIES.md"


def read_attachment(path, sha, observed):
    values = (path, sha, observed)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("An attachment requires an operator-selected path, hash, and observed time")
    return ToolEvidence(read_verified_record(path, sha), observed)


def read_registry():
    raw = REGISTRY.read_bytes()
    entries = []
    for line in raw.decode().splitlines():
        match = re.match(r"^\| (STR-[0-9]{3}) \| ([^|]+?) \|", line)
        if match:
            entries.append(match.groups())
    return hashlib.sha256(raw).hexdigest(), tuple(entries)


def add_evidence_arguments(parser):
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--as-of", type=utc, required=True)
    parser.add_argument("--macro-snapshot", type=Path)
    parser.add_argument("--macro-snapshot-id")
    for record in ("forecast", "calendar"):
        parser.add_argument(f"--{record}", type=Path)
        parser.add_argument(f"--{record}-sha256")
        parser.add_argument(f"--{record}-observed-at", type=utc)


def load_tools(args):
    snapshot = load_market_snapshot(args.snapshot, args.snapshot_id)
    if bool(args.macro_snapshot) != bool(args.macro_snapshot_id):
        raise ValueError("Supply both macro snapshot and trusted content ID")
    macro = load_market_snapshot(args.macro_snapshot, args.macro_snapshot_id) if args.macro_snapshot else None
    sha, registry = read_registry()
    forecast = read_attachment(args.forecast, args.forecast_sha256, args.forecast_observed_at)
    calendar = read_attachment(args.calendar, args.calendar_sha256, args.calendar_observed_at)
    return GoldTools(snapshot, args.as_of, sha, registry, forecast, calendar, macro)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_evidence_arguments(parser)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tools = load_tools(args)
    responses = {}
    declarations = tools.declarations()
    for declaration in declarations:
        name = declaration["function"]["name"]
        arguments = {"symbol": "XAUUSD", **({"strategy_id": "STR-003"} if name == "get_strategy_spec" else {})}
        responses[name] = tools.call(name, arguments)
    report = {"scope": "offline XAUUSD tool contract exercise", "declarations": declarations,
              "responses": responses, "execution_ready": False}
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"{len(responses)} read-only tools; advisory {responses['get_risk_status']['advisory']}")


if __name__ == "__main__":
    main()
