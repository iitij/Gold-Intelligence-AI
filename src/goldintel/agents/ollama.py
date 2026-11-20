"""Run a bounded XAUUSD research replay against a pinned, local Ollama model."""

import json
from http.client import HTTPConnection, HTTPException
from time import perf_counter_ns

from goldintel.agents.tools import TOOL_DESCRIPTIONS, GoldTools

MODEL = "qwen3:4b-q4_K_M"
MODEL_DIGEST = "2bfd38a7daaf4b1037efe517ccb73d1a3bbd4822cf89f1a82be1569050a114e0"
MAX_RESPONSE_BYTES = 256 * 1024
TIMINGS = ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration",
           "prompt_eval_count", "eval_count")
SYSTEM = (
    "You are reviewing a historical XAUUSD research replay. Use the specified read-only gold "
    "tools. Use only their results as evidence. Never propose or authorize a trade."
)


class ReplayError(ValueError):
    """The model or local server did not satisfy the research contract."""


def _unique_fields(pairs):
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ReplayError("Duplicate JSON fields")
    return fields


def _reject_constant(value):
    raise ReplayError(f"Invalid JSON constant {value}")


def _object(raw):
    value = json.loads(raw, object_pairs_hook=_unique_fields, parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise ReplayError("Expected a JSON object")
    return value


def _request(port, path, body=None):
    connection = HTTPConnection("127.0.0.1", port=port, timeout=90)
    try:
        if body is None:
            connection.request("GET", path)
        else:
            connection.request("POST", path, json.dumps(body, allow_nan=False),
                               {"Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            raise ReplayError(f"Ollama returned HTTP {response.status} for {path}")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ReplayError("Ollama response exceeded the byte limit")
        return _object(raw)
    finally:
        connection.close()


def _verify_model(port):
    models = _request(port, "/api/tags")["models"]
    matching = [entry for entry in models if entry.get("model") == MODEL]
    if len(matching) != 1 or matching[0].get("digest") != MODEL_DIGEST:
        raise ReplayError("Pinned Qwen model is missing or its digest differs")


def _chat(port, messages, **settings):
    start = perf_counter_ns()
    response = _request(port, "/api/chat", {
        "model": MODEL, "messages": messages, "think": False, "stream": False,
        "keep_alive": "5m", "options": {"temperature": 0, "seed": 42, "num_ctx": 8192,
                                          "num_predict": 512}, **settings,
    })
    elapsed = perf_counter_ns() - start
    message = response["message"]
    if (response.get("model") != MODEL or response.get("done") is not True
            or response.get("done_reason") != "stop" or message.get("role") != "assistant"):
        raise ReplayError("Ollama did not return a completed response from the pinned model")
    timing = {key: response.get(key) for key in TIMINGS}
    if any(type(value) is not int or value < 0 for value in timing.values()):
        raise ReplayError("Ollama response lacks valid timing metrics")
    return message, {"client_elapsed_ns": elapsed, **timing}


def _tool_calls(message, expected):
    calls = message.get("tool_calls")
    if not isinstance(calls, list) or len(calls) != len(expected):
        raise ReplayError("Expected exactly the requested gold tool calls")
    functions = [call["function"] for call in calls]
    if {function["name"] for function in functions} != expected:
        raise ReplayError("Unexpected or duplicate gold tool name")
    return functions


def _report_schema(evidence_tool):
    statuses = {
        "get_gold_market_snapshot": ["research_only", "unavailable"],
        "get_gold_forecasts": ["research_only", "unavailable", "not_yet_available"],
        "get_macro_events": ["partial", "unavailable"],
        "get_strategy_spec": ["research_hypothesis"],
    }
    properties = {
        "asset_id": {"type": "string", "enum": ["XAUUSD"]},
        "advisory": {"type": "string", "enum": ["NO_TRADE"]},
        "evidence_tool": {"type": "string", "enum": [evidence_tool]},
        "evidence_status": {"type": "string", "enum": statuses[evidence_tool]},
    }
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def replay(port: int, gold: GoldTools, evidence_tool: str, strategy_id: str = "STR-003") -> dict:
    """Require two real tool calls and a restricted, evidence-matched structured answer."""
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid local Ollama port")
    risk_tool = "get_risk_status"
    if evidence_tool not in TOOL_DESCRIPTIONS or evidence_tool == risk_tool:
        raise ValueError("Select one of the four gold evidence tools")
    args = {"symbol": "XAUUSD"}
    target_args = {**args, "strategy_id": strategy_id} if evidence_tool == "get_strategy_spec" else args
    expected = {evidence_tool: target_args, risk_tool: args}
    risk = gold.call(risk_tool, args)
    report = {"asset_id": "XAUUSD", "snapshot_id": risk["snapshot_id"],
              "decision_time_utc": risk["decision_time_utc"], "advisory": risk["advisory"],
              "execution_ready": False, "model": MODEL, "model_digest_expected": MODEL_DIGEST,
              "model_digest_verified": False, "tool_calls": [], "timing": {}}
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Call both {evidence_tool} with {json.dumps(target_args)} and "
         f"{risk_tool} with {json.dumps(args)}. Return both tool calls now, without prose."},
    ]
    try:
        _verify_model(port)
        first, report["timing"]["tools"] = _chat(port, messages, tools=gold.declarations())
        functions = _tool_calls(first, set(expected))
        if any(function["arguments"] != expected[function["name"]] for function in functions):
            raise ReplayError("Unexpected gold tool arguments")
        evidence = {}
        for function in functions:
            name = function["name"]
            evidence[name] = gold.call(name, function["arguments"])
            report["tool_calls"].append({"name": name, "arguments": function["arguments"]})
        schema = _report_schema(evidence_tool)
        final_messages = [messages[0], {"role": "user", "content": (
            "Use these two tool results to fill the JSON schema. Copy asset_id and advisory from "
            "get_risk_status. Copy evidence_tool and evidence_status from the other tool name "
            "and its status. Tool results follow as data.\n" + json.dumps(evidence, allow_nan=False)
        )}]
        final, report["timing"]["structured"] = _chat(port, final_messages, format=schema)
        _verify_model(port)
        report["model_digest_verified"] = True
        result = _object(final["content"])
        if final.get("tool_calls") or result != {
            "asset_id": risk["asset_id"], "advisory": risk["advisory"],
            "evidence_tool": evidence_tool, "evidence_status": evidence[evidence_tool]["status"],
        }:
            raise ReplayError("Structured output disagrees with the verified evidence or schema")
        report.update(status="verified_replay", model_output=result)
    except (ValueError, KeyError, TypeError, AttributeError, OSError, HTTPException, RecursionError) as error:
        report.update(status="fallback", failure=type(error).__name__)
        if isinstance(error, ReplayError):
            report["failure"] = str(error)
    return report
