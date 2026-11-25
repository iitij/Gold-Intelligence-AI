"""Inspect evidence coverage for the registered Headway commission; never score prices."""

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path

from goldintel.research.holdout import read_protocol

PROTOCOL = Path(__file__).resolve().parents[1] / "planning/prospective_holdout_20261118.json"


def utc(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() != timedelta(0):
        raise ValueError("Cost timestamps must be explicit UTC")
    return stamp


def amount(value, *, positive=False):
    if not isinstance(value, str):
        raise ValueError("Cost amounts must be explicit decimal strings")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal cost amount") from exc
    if not number.is_finite() or number < 0 or (positive and not number):
        raise ValueError("Invalid cost amount")
    return number


def verified_file(root, entry):
    relative = Path(entry["path"])
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Cost evidence must be a local file beneath the manifest")
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
            raise ValueError(f"Cost evidence fingerprint differs: {relative}")


def audit(protocol, manifest, root, now):
    if ((manifest["schema_version"], manifest["server"], manifest["symbol"], manifest["currency"])
            != (1, protocol["server"], protocol["symbol"], "USD")):
        raise ValueError("Unexpected registered commission scope")
    start, end = utc(protocol["start_utc"]), utc(protocol["end_exclusive_utc"])
    documented = []
    for row in manifest["intervals"]:
        lo, hi = utc(row["start_utc"]), utc(row["end_exclusive_utc"])
        if not start <= lo < hi <= min(end, now):
            raise ValueError("Cost interval is outside the elapsed registered range")
        if not isinstance(row["account_tier"], str) or not row["account_tier"].strip():
            raise ValueError("Cost interval needs an explicit account tier")
        for field in ("account_terms_evidence", "contract_size_evidence"):
            verified_file(root, row[field])
        per_lot = amount(row["commission_usd_per_side_per_lot"])
        ounces = amount(row["contract_ounces_per_lot"], positive=True)
        per_ounce = per_lot / ounces
        if Fraction(per_ounce) * Fraction(ounces) != Fraction(per_lot):
            raise ValueError("Commission per ounce cannot be represented exactly in the replay input")
        documented.append((lo, hi, per_ounce))
    observations = []
    for row in manifest.get("point_observations", []):
        when = utc(row["observed_at_utc"])
        if not start <= when < end or when > now:
            raise ValueError("Cost observation is outside the elapsed registered range")
        verified_file(root, row["evidence"])
        observations.append({"observed_at_utc": when.isoformat(), "evidence_sha256": row["evidence"]["sha256"]})
    cursor = start
    gaps = []
    values = set()
    for lo, hi, rate in sorted(documented):
        if lo < cursor:
            raise ValueError("Commission evidence intervals overlap")
        if lo > cursor:
            gaps.append([cursor.isoformat(), lo.isoformat()])
        values.add(rate)
        cursor = hi
    if cursor < end:
        gaps.append([cursor.isoformat(), end.isoformat()])
    return {
        "window_start_utc": start.isoformat(), "window_end_exclusive_utc": end.isoformat(),
        "intervals_with_bound_evidence": len(documented), "uncovered_intervals": gaps,
        "point_observations_not_used_as_intervals": observations,
        "distinct_documented_rates_usd_per_side_per_ounce": sorted(str(v) for v in values),
        "complete_interval_coverage": not gaps,
        "constant_commission_candidate": str(next(iter(values))) if not gaps and len(values) == 1 else None,
        "evidence_requires_substantive_review": True, "holdout_scored": False,
        "evaluation_ready": False, "approved_for_trading": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    protocol_hash = PROTOCOL.with_suffix(".sha256").read_text().strip()
    protocol = read_protocol(PROTOCOL, protocol_hash)
    raw = args.manifest.read_bytes()
    now = datetime.now(timezone.utc)
    result = audit(protocol, json.loads(raw), args.manifest.resolve().parent, now)
    record = {"schema_version": 1, "protocol_sha256": protocol_hash,
              "manifest_sha256": hashlib.sha256(raw).hexdigest(), "audited_at_utc": now.isoformat(), **result}
    with args.output.open("x") as output:
        output.write(json.dumps(record, indent=2) + "\n")
    print(f"{result['intervals_with_bound_evidence']} evidence intervals; "
          f"{len(result['uncovered_intervals'])} gaps; candidate={result['constant_commission_candidate']}")
    return 0 if result["constant_commission_candidate"] is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
