"""Versioned, content-addressed, past-only XAUUSD research input snapshots."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from goldintel.domain import MarketQuote
from goldintel.research.point_in_time import (
    MAX_STALENESS,
    CompletedGoldBar,
    EconomicObservation,
    PointInTimeError,
    _require_utc,
    latest_released_observations,
    make_gold_features,
)


@dataclass(frozen=True)
class SnapshotEvidence:
    source_id: str
    sha256: str

    def __post_init__(self):
        if not self.source_id.strip() or not re.fullmatch(r"[a-f0-9]{64}", self.sha256):
            raise PointInTimeError("Snapshot evidence requires a source ID and SHA256")


@dataclass(frozen=True)
class MarketSnapshot:
    snapshot_id: str
    canonical_payload: str

    def as_dict(self) -> dict:
        return {"snapshot_id": self.snapshot_id, **json.loads(self.canonical_payload)}

    def status_at(self, requested_at_utc: datetime) -> dict:
        """Expired cached packets cannot become fresh when a downstream refresh fails."""
        _require_utc(requested_at_utc, "snapshot inspection time")
        if hashlib.sha256(self.canonical_payload.encode()).hexdigest() != self.snapshot_id:
            raise PointInTimeError("Snapshot content fingerprint mismatch")
        data = json.loads(self.canonical_payload)
        if data["schema_version"] != 1 or data["execution_ready"] is not False:
            raise PointInTimeError("Unsupported snapshot schema or execution state")
        decision = datetime.fromisoformat(data["decision_at_utc"])
        expiry = datetime.fromisoformat(data["quote"]["observed_at_utc"]) + timedelta(
            microseconds=data["policy"]["max_quote_age_microseconds"]
        )
        if data["features"]:
            for timeframe in MAX_STALENESS:
                latest_close = max(datetime.fromisoformat(bar["closed_at_utc"]) for bar in data["bars"]
                                   if bar["timeframe"] == timeframe)
                expiry = min(expiry, latest_close + MAX_STALENESS[timeframe])
        blockers = list(data["blockers"])
        if requested_at_utc < decision:
            blockers.append("snapshot_not_yet_available")
        if requested_at_utc > expiry:
            blockers.append("snapshot_expired")
        return {"snapshot_id": self.snapshot_id, "requested_at_utc": requested_at_utc.isoformat(),
                "valid_until_utc": expiry.isoformat(), "research_inputs_usable": not blockers,
                "blockers": blockers, "execution_ready": False}


def load_market_snapshot(path: Path, expected_snapshot_id: str) -> MarketSnapshot:
    """Load using a previously trusted content ID, then check freshness with status_at."""
    data = json.loads(path.read_text())
    if data.pop("snapshot_id") != expected_snapshot_id:
        raise PointInTimeError("Unexpected snapshot identity")
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
    snapshot = MarketSnapshot(expected_snapshot_id, canonical)
    snapshot.status_at(datetime.fromisoformat(data["decision_at_utc"]))
    return snapshot


def build_market_snapshot(
    *, decision_at_utc: datetime, quote: MarketQuote, quote_available_at_utc: datetime,
    quote_source_id: str, evidence: Sequence[SnapshotEvidence],
    bars: Sequence[CompletedGoldBar] = (), observations: Sequence[EconomicObservation] = (),
    calendar_coverage_verified: bool = False, calendar_source_id: str | None = None,
    max_quote_age: timedelta = timedelta(seconds=60),
) -> MarketSnapshot:
    """Create a research packet; missing/stale inputs block completeness, never grant execution.

    quote.observed_at_utc denotes actual UTC observation, not a broker timestamp
    with a guessed offset. Source timestamps may be retained in separate raw evidence.
    Future bars/releases are excluded before duplicate and provenance validation.
    """
    for name, value in (("decision", decision_at_utc), ("quote observation", quote.observed_at_utc),
                        ("quote availability", quote_available_at_utc)):
        _require_utc(value, name)
    if not all(isinstance(value, Decimal) and value.is_finite() for value in (quote.bid, quote.ask)):
        raise PointInTimeError("Snapshot prices must be finite Decimals")
    if (quote.symbol != "XAUUSD" or not 0 < quote.bid <= quote.ask
            or type(quote.source_verified) is not bool):
        raise PointInTimeError("Snapshot requires valid verified-state XAUUSD Bid/Ask")
    if not quote.observed_at_utc <= quote_available_at_utc <= decision_at_utc:
        raise PointInTimeError("Quote was not historically available at the decision")
    if max_quote_age <= timedelta(0) or type(calendar_coverage_verified) is not bool:
        raise PointInTimeError("Invalid snapshot freshness or calendar policy")
    sources = {item.source_id: item.sha256 for item in evidence}
    if len(sources) != len(evidence) or quote_source_id not in sources:
        raise PointInTimeError("Duplicate evidence IDs or missing quote provenance")
    if calendar_coverage_verified and calendar_source_id not in sources:
        raise PointInTimeError("Verified calendar coverage requires source provenance")
    available_bars = sorted((bar for bar in bars if bar.closed_at_utc <= decision_at_utc
                             and bar.available_at_utc <= decision_at_utc),
                            key=lambda bar: (bar.timeframe, bar.closed_at_utc))
    if len({(bar.timeframe, bar.closed_at_utc) for bar in available_bars}) != len(available_bars):
        raise PointInTimeError("Duplicate historically available bars")
    available_observations = [item for item in observations if item.available_at_utc <= decision_at_utc]
    latest = latest_released_observations(available_observations, decision_at_utc)
    if any(bar.source_id not in sources for bar in available_bars) or any(
        item.source_id not in sources for item in available_observations
    ):
        raise PointInTimeError("Missing historically available input provenance")
    blockers = []
    if not quote.source_verified:
        blockers.append("quote_source_unverified")
    if decision_at_utc - quote.observed_at_utc > max_quote_age:
        blockers.append("stale_quote")
    if not calendar_coverage_verified:
        blockers.append("calendar_coverage_unverified")
    features = {}
    feature_evidence = []
    try:
        calculated = make_gold_features(available_bars, decision_at_utc)
        features = {name: str(value) for name, value in calculated.values}
        feature_evidence = [list(item) for item in calculated.evidence]
    except PointInTimeError:
        blockers.append("completed_bar_features_unavailable")
    used_sources = {quote_source_id, *(bar.source_id for bar in available_bars),
                    *(item.source_id for item in latest.values())}
    if calendar_coverage_verified:
        used_sources.add(calendar_source_id)
    payload = {
        "schema_version": 1, "asset_id": "XAUUSD",
        "decision_at_utc": decision_at_utc.isoformat(),
        "quote": {"observed_at_utc": quote.observed_at_utc.isoformat(),
                  "available_at_utc": quote_available_at_utc.isoformat(),
                  "bid": str(quote.bid), "ask": str(quote.ask),
                  "source_id": quote_source_id, "source_verified": quote.source_verified},
        "policy": {"max_quote_age_microseconds": max_quote_age // timedelta(microseconds=1),
                   "calendar_coverage_verified": calendar_coverage_verified,
                   "calendar_source_id": calendar_source_id if calendar_coverage_verified else None},
        "feature_profile": "completed_m15_h1_h4_research_v1",
        "features": features, "feature_evidence": feature_evidence,
        "bars": [{"timeframe": bar.timeframe, "opened_at_utc": bar.opened_at_utc.isoformat(),
                  "closed_at_utc": bar.closed_at_utc.isoformat(),
                  "available_at_utc": bar.available_at_utc.isoformat(),
                  **{name: str(getattr(bar, name)) for name in ("open", "high", "low", "close")},
                  "source_id": bar.source_id} for bar in available_bars],
        "released_observations": [
            {"series_id": item.series_id, "reference_at_utc": item.reference_at_utc.isoformat(),
             "available_at_utc": item.available_at_utc.isoformat(), "value": str(item.value),
             "source_id": item.source_id, "revision_id": item.revision_id}
            for _, item in sorted(latest.items())
        ],
        "source_sha256": {key: sources[key] for key in sorted(used_sources)},
        "research_inputs_complete": not blockers, "blockers": blockers,
        "execution_ready": False,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return MarketSnapshot(hashlib.sha256(canonical.encode()).hexdigest(), canonical)
