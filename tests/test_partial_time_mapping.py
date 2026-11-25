"""Partial clock conversion must preserve every original row and never invent coverage."""
import csv
import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from goldintel.data.mt5_csv import COLUMNS


@pytest.fixture
def mapper():
    path = Path(__file__).resolve().parents[1] / "scripts/map_partial_broker_time.py"
    spec = importlib.util.spec_from_file_location("partial_mapping", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source_and_policy(tmp_path):
    source = tmp_path / "bars.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        for time in ("09:00:00", "09:15:00", "09:30:00", "09:45:00"):
            writer.writerow(["XAUUSD", "M15", f"2025.01.01 {time}",
                             "2000.000", "2002.00", "1999.00", "2001.000", "12", "25", "0"])
    config = {
        "schema_version": 1, "symbol": "XAUUSD",
        "status": "research_inference_from_official_notices_and_archived_session_bounds",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "sources": {"synthetic": {"url": "synthetic_test_only"}},
        "intervals": [{"id": "known", "native_start": "2025-01-01T09:15:00",
                       "native_end_exclusive": "2025-01-01T09:45:00", "offset_seconds": 7200,
                       "sources": ["synthetic"]}],
    }
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(config))
    return source, policy, config


def test_partial_conversion_preserves_all_rows_and_original_precision(mapper, source_and_policy, tmp_path):
    source, policy, _ = source_and_policy
    output = tmp_path / "mapped"
    report = mapper.map_source(source, policy, output)
    assert report["mapped_rows"] == report["unmapped_rows"] == 2
    assert not report["historical_utc_verified"] and not report["approved_for_training_or_trading"]
    with (output / "mapped.csv").open(newline="") as stream:
        known = list(csv.DictReader(stream))
    with (output / "unmapped.csv").open(newline="") as stream:
        unknown = list(csv.DictReader(stream))
    assert known[0]["timestamp_utc_inferred"] == "2025-01-01T07:15:00+00:00"
    assert [row["source_row"] for row in unknown] == ["0", "3"]
    restored = [{column: row[column] for column in COLUMNS}
                for row in sorted(known + unknown, key=lambda row: int(row["source_row"]))]
    with source.open(encoding="utf-8-sig", newline="") as stream:
        assert restored == list(csv.DictReader(stream))
    with pytest.raises(FileExistsError):
        mapper.map_source(source, policy, output)


def test_unverified_other_feed_cannot_use_broker_policy(mapper, source_and_policy, tmp_path):
    source, policy, config = source_and_policy
    config["source_sha256"] = "0" * 64
    policy.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="Broker source fingerprint"):
        mapper.map_source(source, policy, tmp_path / "wrong-source")
    assert not (tmp_path / "wrong-source").exists()


def test_overlapping_or_aware_native_intervals_rejected(mapper, source_and_policy):
    _, _, config = source_and_policy
    record = deepcopy(config["intervals"][0])
    record["id"] = "overlap"
    config["intervals"].append(record)
    with pytest.raises(ValueError, match="overlapping"):
        mapper.intervals_from_config(config)
    config["intervals"] = [record]
    record["native_start"] += "+00:00"
    with pytest.raises(ValueError, match="Invalid interval"):
        mapper.intervals_from_config(config)


def test_bad_offset_transition_cannot_reorder_utc_bars(mapper, source_and_policy, tmp_path):
    source, policy, config = source_and_policy
    config["intervals"] = [
        {"id": "before", "native_start": "2025-01-01T09:00:00",
         "native_end_exclusive": "2025-01-01T09:15:00", "offset_seconds": 7200, "sources": ["synthetic"]},
        {"id": "after", "native_start": "2025-01-01T09:15:00",
         "native_end_exclusive": "2025-01-01T10:00:00", "offset_seconds": 10800, "sources": ["synthetic"]},
    ]
    policy.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="chronological in UTC"):
        mapper.map_source(source, policy, tmp_path / "bad-transition")
    assert not (tmp_path / "bad-transition/manifest.json").exists()
