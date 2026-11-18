"""Bind the local agent's read-only XAUUSD tools to trusted evidence and one UTC instant."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from goldintel.data.snapshot import MarketSnapshot
from goldintel.research.point_in_time import PointInTimeError, _require_utc

TOOL_DESCRIPTIONS = {
    "get_gold_market_snapshot": "Read the verified XAUUSD Bid/Ask, completed candles and price features.",
    "get_gold_forecasts": "Read the available frozen XAUUSD research probabilities.",
    "get_macro_events": "Read observed macro values and calendar coverage for the market snapshot.",
    "get_strategy_spec": "Read one XAUUSD research hypothesis from the strategy registry.",
    "get_risk_status": "Read deterministic research abstention and evidence blockers.",
}
STRATEGIES = tuple(f"STR-{n:03d}" for n in range(1, 8))
MODEL_CASES = {(model, h) for model in ("LightGBM", "CatBoost") for h in (1, 4, 16)}


def utc(value):
    stamp = datetime.fromisoformat(value)
    _require_utc(stamp, "evidence time")
    return stamp


def read_verified_record(path: Path, expected_sha256: str) -> str:
    """Hash bytes before interpreting the operator-selected evidence document."""
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise PointInTimeError("Evidence requires a trusted SHA256")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise PointInTimeError("Unexpected evidence fingerprint")
    record = json.loads(raw)
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class ToolEvidence:
    canonical_record: str
    available_at_utc: datetime

    def __post_init__(self):
        _require_utc(self.available_at_utc, "tool evidence availability")


@dataclass(frozen=True)
class GoldTools:
    snapshot: MarketSnapshot
    decision_time_utc: datetime
    strategy_registry_sha256: str
    strategies: tuple[tuple[str, str], ...]
    forecasts: ToolEvidence | None = None
    calendar: ToolEvidence | None = None
    macro_snapshot: MarketSnapshot | None = None

    def __post_init__(self):
        _require_utc(self.decision_time_utc, "agent decision time")
        self.snapshot.status_at(self.decision_time_utc)
        core = self.snapshot.as_dict()
        if core["asset_id"] != "XAUUSD" or core["released_observations"]:
            raise PointInTimeError("Expected a direct price snapshot for XAUUSD")
        if (tuple(i for i, _ in self.strategies) != STRATEGIES
                or not re.fullmatch(r"[a-f0-9]{64}", self.strategy_registry_sha256)):
            raise PointInTimeError("Invalid XAUUSD strategy registry")
        if self.macro_snapshot is not None:
            self.macro_snapshot.status_at(self.decision_time_utc)
            extended = self.macro_snapshot.as_dict()
            if (any(extended[key] != core[key] for key in core
                    if key not in {"snapshot_id", "released_observations", "source_sha256"})
                    or any(extended["source_sha256"].get(key) != value
                           for key, value in core["source_sha256"].items())):
                raise PointInTimeError("Macro observations belong to a different market snapshot")

    @staticmethod
    def declarations():
        declarations = []
        for name, description in TOOL_DESCRIPTIONS.items():
            parameters = {"symbol": {"type": "string", "enum": ["XAUUSD"]}}
            if name == "get_strategy_spec":
                parameters["strategy_id"] = {"type": "string", "enum": list(STRATEGIES)}
            declarations.append({"type": "function", "function": {
                "name": name, "description": description, "parameters": {
                    "type": "object", "properties": parameters, "required": list(parameters),
                    "additionalProperties": False,
                },
            }})
        return declarations

    def _envelope(self):
        price_time = utc(self.snapshot.as_dict()["decision_at_utc"])
        return {
            "schema_version": 1, "asset_id": "XAUUSD",
            "decision_time_utc": self.decision_time_utc.isoformat(),
            "snapshot_id": self.snapshot.snapshot_id if price_time <= self.decision_time_utc else None,
            "execution_ready": False,
        }

    def _price_status(self):
        status = self.snapshot.status_at(self.decision_time_utc)
        invalid = {"snapshot_not_yet_available", "snapshot_expired", "stale_quote", "quote_source_unverified"}
        return status, not invalid.intersection(status["blockers"])

    def _forecast_payload(self, prices_valid):
        if not prices_valid or self.forecasts is None:
            return {"status": "unavailable", "forecast_probabilities": []}
        if self.forecasts.available_at_utc > self.decision_time_utc:
            return {"status": "not_yet_available", "forecast_probabilities": []}
        raw = json.loads(self.forecasts.canonical_record)
        if (raw["schema_version"] != 1 or raw["status"] != "research_attachment"
                or raw["snapshot_id"] != self.snapshot.snapshot_id or raw["execution_ready"] is not False
                or not utc(self.snapshot.as_dict()["decision_at_utc"]) <= utc(raw["reconstructed_at_utc"])
                <= self.forecasts.available_at_utc):
            raise PointInTimeError("Invalid forecast evidence timing or snapshot binding")
        probabilities = raw["forecast_probabilities"]
        cases = {(row["model"], row["horizon_bars"]) for row in probabilities}
        if len(probabilities) != len(MODEL_CASES) or cases != MODEL_CASES:
            raise PointInTimeError("Expected the six frozen classifier cases")
        projected = []
        for row in probabilities:
            p = row["calibrated_up_probability"]
            if (type(row["horizon_bars"]) is not int or type(p) not in (float, int)
                    or not 0 <= p <= 1 or not re.fullmatch(r"[a-f0-9]{64}", row["model_sha256"])):
                raise PointInTimeError("Invalid frozen classifier probability or fingerprint")
            projected.append({"model": row["model"], "horizon_bars": row["horizon_bars"],
                              "calibrated_up_probability": p, "model_sha256": row["model_sha256"]})
        return {"status": "research_only", "forecast_probabilities": projected,
                "available_at_utc": self.forecasts.available_at_utc.isoformat()}

    def _macro_payload(self, prices_valid):
        if not prices_valid:
            return {"status": "unavailable", "released_observations": [], "scheduled_events": []}
        snapshot = self.macro_snapshot or self.snapshot
        data = snapshot.as_dict()
        events = []
        if self.calendar is not None and self.calendar.available_at_utc <= self.decision_time_utc:
            row = json.loads(self.calendar.canonical_record)
            assessment = row["assessment_at_snapshot"]
            if (row["schema_version"] != 1 or row["snapshot_id"] != self.snapshot.snapshot_id
                    or row["execution_ready"] is not False
                    or assessment["decision_at_utc"] != self.snapshot.as_dict()["decision_at_utc"]
                    or utc(assessment["decision_at_utc"]) > self.calendar.available_at_utc):
                raise PointInTimeError("Invalid calendar evidence time or snapshot binding")
            event = row["event"]
            known = utc(event["schedule_known_at_utc"])
            if known <= utc(assessment["decision_at_utc"]):
                when = utc(event["official_release_utc"])
                if event["event_id"] != f"fomc-minutes-{when.date().isoformat()}":
                    raise PointInTimeError("Unexpected scheduled event identity")
                events.append({"event_id": event["event_id"], "schedule_known_at_utc": known.isoformat(),
                               "scheduled_at_utc": when.isoformat()})
        return {
            "status": "partial", "macro_snapshot_id": snapshot.snapshot_id,
            "calendar_coverage_verified": False,
            "released_observations": data["released_observations"], "scheduled_events": events,
        }

    def call(self, name, arguments):
        """Only symbol and fixed strategy IDs are supplied by the agent."""
        if type(name) is not str or name not in TOOL_DESCRIPTIONS:
            raise PointInTimeError("Unsupported gold tool")
        expected = {"symbol", "strategy_id"} if name == "get_strategy_spec" else {"symbol"}
        if not isinstance(arguments, dict) or set(arguments) != expected or arguments["symbol"] != "XAUUSD":
            raise PointInTimeError("Bad tool arguments: XAUUSD scope and declared fields required")
        base = self._envelope()
        if name == "get_strategy_spec":
            entry = dict(self.strategies).get(arguments["strategy_id"]) if isinstance(arguments["strategy_id"], str) else None
            if entry is None:
                raise PointInTimeError("Unsupported gold strategy")
            return {**base, "strategy_id": arguments["strategy_id"], "hypothesis": entry,
                    "strategy_registry_sha256": self.strategy_registry_sha256, "status": "research_hypothesis"}
        status, prices_valid = self._price_status()
        if name == "get_gold_market_snapshot":
            if not prices_valid:
                return {**base, "status": "unavailable", "blockers": status["blockers"]}
            data = self.snapshot.as_dict()
            return {**base, "status": "research_only", "blockers": status["blockers"],
                    **{key: data[key] for key in ("quote", "bars", "features", "source_sha256")}}
        if name == "get_gold_forecasts":
            return {**base, **self._forecast_payload(prices_valid)}
        if name == "get_macro_events":
            return {**base, **self._macro_payload(prices_valid)}

        blockers = [*status["blockers"], "models_not_approved", "account_risk_inputs_unavailable"]
        try:
            if self._forecast_payload(prices_valid)["status"] != "research_only":
                blockers.append("forecast_unavailable")
        except (ValueError, TypeError, KeyError):
            blockers.append("forecast_evidence_invalid")
        return {**base, "advisory": "NO_TRADE", "blockers": blockers}
