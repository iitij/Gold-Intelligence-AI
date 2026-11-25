"""Build a quote-only research packet from a direct host-timed observation."""
import argparse
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from goldintel.data.snapshot import SnapshotEvidence, build_market_snapshot
from goldintel.domain import MarketQuote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--host-clock-evidence", type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.capture.read_text())
    clock = json.loads(args.host_clock_evidence.read_text())
    if raw["schema_version"] != 1 or raw["kind"] != "observed_headway_quote" or raw["server"] != "Headway-Demo":
        raise ValueError("Unexpected observed-quote schema or source")
    before, after = (datetime.fromisoformat(raw[key]) for key in ("host_utc_before", "host_utc_after"))
    if not (datetime.fromisoformat(clock["checked_before_utc"]) <= before <= after
            <= datetime.fromisoformat(clock["checked_after_utc"])):
        raise ValueError("Host clock checks do not bracket quote capture")
    if raw["observed_at_utc"] != raw["host_utc_after"] or type(raw["source_verified"]) is not bool:
        raise ValueError("Quote observation semantics or verification state mismatch")
    verified = raw["source_verified"] and clock["before"] == clock["after"] == "NTPSynchronized=yes"
    snapshot = build_market_snapshot(
        decision_at_utc=after,
        quote=MarketQuote(raw["symbol"], after, Decimal(raw["bid"]), Decimal(raw["ask"]), verified),
        quote_available_at_utc=after, quote_source_id="direct_headway_observation",
        evidence=[SnapshotEvidence("direct_headway_observation", hashlib.sha256(args.capture.read_bytes()).hexdigest())],
    )
    output = snapshot.as_dict()
    with args.output.open("x") as stream:
        stream.write(json.dumps(output, indent=2, allow_nan=False) + "\n")
    receipt = {
        "snapshot_id": snapshot.snapshot_id,
        "capture_sha256": hashlib.sha256(args.capture.read_bytes()).hexdigest(),
        "host_clock_evidence_sha256": hashlib.sha256(args.host_clock_evidence.read_bytes()).hexdigest(),
        "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "Direct quote only; completed-bar and macro inputs not supplied",
    }
    with args.output.with_suffix(".receipt.json").open("x") as stream:
        stream.write(json.dumps(receipt, indent=2) + "\n")
    print(f"Snapshot {snapshot.snapshot_id}; blockers: {', '.join(output['blockers'])}")


if __name__ == "__main__":
    main()
