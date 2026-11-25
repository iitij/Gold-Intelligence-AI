"""Verify XAUUSD tool scope, time injection, and abstention."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

from goldintel.agents import ollama
from goldintel.agents.tools import MODEL_CASES, STRATEGIES, GoldTools, ToolEvidence
from goldintel.data.snapshot import SnapshotEvidence, build_market_snapshot
from goldintel.domain import MarketQuote
from goldintel.research.point_in_time import PointInTimeError

T = datetime(2026, 11, 18, 20, tzinfo=timezone.utc)
ARGS = {"symbol": "XAUUSD"}


@pytest.fixture
def gold():
    snapshot = build_market_snapshot(
        decision_at_utc=T, quote=MarketQuote("XAUUSD", T, Decimal("3700"), Decimal("3701"), True),
        quote_available_at_utc=T, quote_source_id="quote", evidence=[SnapshotEvidence("quote", "a" * 64)],
    )
    record = {"schema_version": 1, "status": "research_attachment", "snapshot_id": snapshot.snapshot_id,
              "execution_ready": False, "reconstructed_at_utc": T.isoformat(),
              "forecast_probabilities": [{"model": m, "horizon_bars": h, "calibrated_up_probability": .5,
                                           "model_sha256": "b" * 64} for m, h in sorted(MODEL_CASES)]}
    forecast = ToolEvidence(json.dumps(record), T + timedelta(seconds=1))
    return GoldTools(snapshot, T + timedelta(seconds=2), "c" * 64, tuple((s, s) for s in STRATEGIES), forecast)


def test_tool_definitions_reject_unlisted_calls_and_model_time_injection(gold):
    assert len(gold.declarations()) == 5
    for declaration in gold.declarations():
        schema = declaration["function"]["parameters"]
        assert schema["additionalProperties"] is False
        assert schema["properties"]["symbol"]["enum"] == ["XAUUSD"]
    for name, args in [
        ("get_stock_data", ARGS), ("place_order", ARGS),
        ("get_gold_market_snapshot", {"symbol": "EURUSD"}),
        ("get_gold_market_snapshot", {**ARGS, "as_of": T.isoformat()}),
        ("get_gold_forecasts", {**ARGS, "path": "/tmp/read"}),
        ("get_strategy_spec", {**ARGS, "strategy_id": "STR-999"}),
    ]:
        with pytest.raises(PointInTimeError):
            gold.call(name, args)


def test_probabilities_and_prices_appear_only_at_correct_time_and_expire(gold):
    before = replace(gold, decision_time_utc=T - timedelta(microseconds=1))
    unavailable = before.call("get_gold_market_snapshot", ARGS)
    assert unavailable["snapshot_id"] is None and "quote" not in unavailable
    at_snapshot = replace(gold, decision_time_utc=T)
    assert at_snapshot.call("get_gold_forecasts", ARGS)["status"] == "not_yet_available"
    available = gold.call("get_gold_forecasts", ARGS)
    assert len(available["forecast_probabilities"]) == 6
    assert gold.call("get_risk_status", ARGS)["advisory"] == "NO_TRADE"
    expired = replace(gold, decision_time_utc=T + timedelta(seconds=61))
    assert expired.call("get_gold_forecasts", ARGS)["forecast_probabilities"] == []
    assert expired.call("get_macro_events", ARGS)["released_observations"] == []
    assert "snapshot_expired" in expired.call("get_risk_status", ARGS)["blockers"]


def test_misbound_forecast_cannot_make_risk_status_tradable(gold):
    raw = json.loads(gold.forecasts.canonical_record)
    raw["snapshot_id"] = "0" * 64
    altered = replace(gold, forecasts=replace(gold.forecasts, canonical_record=json.dumps(raw)))
    with pytest.raises(PointInTimeError, match="snapshot binding"):
        altered.call("get_gold_forecasts", ARGS)
    status = altered.call("get_risk_status", ARGS)
    assert status["advisory"] == "NO_TRADE"
    assert "forecast_evidence_invalid" in status["blockers"]
    assert not status["execution_ready"]


def test_ollama_replay_checks_real_tool_results_and_rejects_invalid_outputs(gold):
    target = "get_gold_forecasts"
    response = {"asset_id": "XAUUSD", "advisory": "NO_TRADE",
                "evidence_tool": target, "evidence_status": "research_only"}
    timings = dict.fromkeys(ollama.TIMINGS, 42)
    settings = {"scenario": "good", "posts": []}

    class MockOllama(BaseHTTPRequestHandler):
        def reply(self, payload):
            wire = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(wire)))
            self.end_headers()
            self.wfile.write(wire)

        def do_GET(self):
            assert self.path == "/api/tags"
            digest = "0" * 64 if settings["scenario"] == "digest" else ollama.MODEL_DIGEST
            self.reply({"models": [{"model": ollama.MODEL, "digest": digest}]})

        def do_POST(self):
            assert self.path == "/api/chat"
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            settings["posts"].append(payload)
            if "tools" in payload:
                arguments = {**ARGS, "path": "/tmp/evidence"} if settings["scenario"] == "arguments" else ARGS
                content = {"tool_calls": [
                    {"function": {"name": target, "arguments": arguments}},
                    {"function": {"name": "get_risk_status", "arguments": ARGS}},
                ]}
            else:
                result = json.dumps(response)
                if settings["scenario"] == "status":
                    result = json.dumps({**response, "evidence_status": "unavailable"})
                elif settings["scenario"] == "duplicate":
                    result = result[:-1] + ', "advisory": "NO_TRADE"}'
                content = {"content": result}
            self.reply({"model": ollama.MODEL, "message": {"role": "assistant", **content},
                        "done": True, "done_reason": "stop", **timings})

    with HTTPServer(("127.0.0.1", 0), MockOllama) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_port
            report = ollama.replay(port, gold, target)
            assert report["status"] == "verified_replay"
            assert report["model_output"] == response and report["model_digest_verified"]
            assert report["timing"]["structured"]["eval_count"] == 42
            first, second = settings["posts"]
            assert first["tools"] == gold.declarations()
            assert second["format"]["additionalProperties"] is False
            assert "calibrated_up_probability" in second["messages"][1]["content"]
            for scenario, expected_posts in [("digest", 0), ("arguments", 1), ("status", 2), ("duplicate", 2)]:
                settings.update(scenario=scenario, posts=[])
                report = ollama.replay(port, gold, target)
                assert report["status"] == "fallback"
                assert report["advisory"] == "NO_TRADE" and not report["execution_ready"]
                assert "model_output" not in report
                assert len(settings["posts"]) == expected_posts
        finally:
            server.shutdown()
            thread.join(timeout=2)
