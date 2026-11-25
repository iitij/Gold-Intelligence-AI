"""Snapshot identity, causal availability and missing-context failures."""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from goldintel.data.snapshot import SnapshotEvidence, build_market_snapshot, load_market_snapshot
from goldintel.domain import MarketQuote
from goldintel.research.point_in_time import CompletedGoldBar, EconomicObservation, PointInTimeError

NOW = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
QUOTE = MarketQuote("XAUUSD", NOW, D("3700"), D("3700.40"), True)
EVIDENCE = tuple(SnapshotEvidence(name, str(index) * 64)
                 for index, name in enumerate(("quotes", "bars", "calendar", "macro")))


def bars():
    result = []
    for frame, minutes, age in (("M15", 15, 15), ("M15", 15, 0), ("H1", 60, 0), ("H4", 240, 0)):
        end = NOW - timedelta(minutes=age)
        result.append(CompletedGoldBar(frame, end - timedelta(minutes=minutes), end, end,
                                      D("3699"), D("3702"), D("3698"), D("3700"), "bars"))
    return result


def make(**changes):
    params = dict(decision_at_utc=NOW, quote=QUOTE, quote_available_at_utc=NOW,
                  quote_source_id="quotes", evidence=EVIDENCE, bars=bars(),
                  calendar_coverage_verified=True, calendar_source_id="calendar")
    params.update(changes)
    return build_market_snapshot(**params)


def test_snapshot_is_reproducible_and_detached_from_mutated_views():
    first = make()
    second = make(bars=list(reversed(bars())), evidence=list(reversed(EVIDENCE)))
    assert first == second
    view = first.as_dict()
    assert view["research_inputs_complete"] and not view["execution_ready"]
    assert view["feature_profile"] == "completed_m15_h1_h4_research_v1"
    view["features"]["m15_return_1"] = "999"
    assert first.as_dict()["features"]["m15_return_1"] == "0"


def test_future_data_and_its_evidence_cannot_change_past_snapshot():
    future_bar = replace(bars()[1], opened_at_utc=NOW, closed_at_utc=NOW + timedelta(minutes=15),
                         available_at_utc=NOW + timedelta(minutes=15), source_id="future")
    release = EconomicObservation("CPI", NOW - timedelta(days=30), NOW + timedelta(seconds=1),
                                  D("5"), "future", "v1")
    first = make()
    second = make(bars=bars() + [future_bar], observations=[release],
                  evidence=(*EVIDENCE, SnapshotEvidence("future", "f" * 64)))
    assert first == second


def test_missing_stale_or_unverified_context_blocks_completeness():
    snapshot = make(bars=(), calendar_coverage_verified=False,
                    quote=replace(QUOTE, observed_at_utc=NOW - timedelta(minutes=2), source_verified=False))
    assert set(snapshot.as_dict()["blockers"]) == {
        "quote_source_unverified", "stale_quote", "calendar_coverage_unverified",
        "completed_bar_features_unavailable",
    }
    assert not snapshot.as_dict()["research_inputs_complete"]


def test_revisions_use_only_available_release_and_contradictions_rejected():
    first = EconomicObservation("CPI", NOW - timedelta(days=30), NOW - timedelta(days=1),
                                D("2"), "macro", "v1")
    revision = replace(first, available_at_utc=NOW + timedelta(seconds=1), value=D("9"), revision_id="v2")
    data = make(observations=[revision, first]).as_dict()
    assert data["released_observations"][0]["value"] == "2"
    with pytest.raises(PointInTimeError, match="Duplicate economic"):
        make(observations=[first, replace(first, value=D("7"))])


def test_future_quote_or_missing_provenance_rejected():
    with pytest.raises(PointInTimeError, match="available"):
        make(quote_available_at_utc=NOW + timedelta(seconds=1))
    with pytest.raises(PointInTimeError, match="provenance"):
        make(evidence=EVIDENCE[:1])
    with pytest.raises(PointInTimeError, match="Duplicate historically"):
        make(bars=bars() + [bars()[0]])
    with pytest.raises(PointInTimeError, match="finite Decimals"):
        make(quote=replace(QUOTE, bid=D("NaN")))


def test_cached_snapshot_expires_even_when_no_replacement_is_available():
    snapshot = make()
    assert snapshot.status_at(NOW + timedelta(seconds=60))["research_inputs_usable"]
    late = snapshot.status_at(NOW + timedelta(seconds=60, microseconds=1))
    assert not late["research_inputs_usable"]
    assert late["blockers"] == ["snapshot_expired"]
    assert snapshot.status_at(NOW - timedelta(microseconds=1))["blockers"] == ["snapshot_not_yet_available"]
    corrupted = replace(snapshot, canonical_payload=snapshot.canonical_payload.replace('"3700"', '"9999"'))
    with pytest.raises(PointInTimeError, match="fingerprint"):
        corrupted.status_at(NOW)


def test_snapshot_expiry_also_respects_its_earliest_bar_deadline():
    history = bars()
    age = timedelta(hours=12, seconds=-30)
    h4 = history[-1]
    history[-1] = replace(h4, opened_at_utc=h4.opened_at_utc - age,
                          closed_at_utc=h4.closed_at_utc - age,
                          available_at_utc=h4.available_at_utc - age)
    snapshot = make(bars=history)
    assert snapshot.status_at(NOW + timedelta(seconds=30))["research_inputs_usable"]
    assert not snapshot.status_at(NOW + timedelta(seconds=31))["research_inputs_usable"]


def test_saved_packet_requires_trusted_identity_and_unchanged_content(tmp_path):
    snapshot = make()
    path = tmp_path / "snapshot.json"
    document = snapshot.as_dict()
    path.write_text(json.dumps(document))
    assert load_market_snapshot(path, snapshot.snapshot_id) == snapshot
    with pytest.raises(PointInTimeError, match="identity"):
        load_market_snapshot(path, "f" * 64)
    document["quote"]["bid"] = "1"
    path.write_text(json.dumps(document))
    with pytest.raises(PointInTimeError, match="fingerprint"):
        load_market_snapshot(path, snapshot.snapshot_id)
