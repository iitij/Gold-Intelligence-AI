"""Fail-closed static policy: owned research code may not call broker-trade APIs.

This is a *capability regression tripwire*, not a complete security scanner.
It intentionally inspects only first-party src/goldintel. Vendored code is
untrusted and is not imported or executed by this test.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src/goldintel"
BANNED_MODULES = {"MetaTrader5", "mt5linux"}
BANNED_CALLS = {
    "order_send", "order_send_async", "OrderSend", "OrderSendAsync",
    "position_close", "positions_close", "trade_order_send",
    "MqlTradeRequest",
}
BANNED_BUILTINS = {"eval", "exec", "__import__"}
BANNED_UNSAFE_DESERIALIZATION = {"pickle.load", "pickle.loads"}


class CoreSafetyViolation(ValueError):
    """First-party code contains an unapproved privileged execution pattern."""


def _attr_name(obj: ast.expr) -> str | None:
    if isinstance(obj, ast.Name):
        return obj.id
    if isinstance(obj, ast.Attribute):
        parent = _attr_name(obj.value)
        return f"{parent}.{obj.attr}" if parent else obj.attr
    return None


def check_code(source: str, filename: str = "<source>") -> None:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        raise CoreSafetyViolation("Invalid first-party Python syntax") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for part in node.names:
                if part.name.split(".")[0] in BANNED_MODULES:
                    raise CoreSafetyViolation(
                        f"{filename}:{node.lineno}: direct broker library import prohibited"
                    )
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in BANNED_MODULES:
                raise CoreSafetyViolation(
                    f"{filename}:{node.lineno}: direct broker library import prohibited"
                )
        elif isinstance(node, ast.Call):
            called = _attr_name(node.func) or ""
            leaf = called.rsplit(".", 1)[-1]
            if leaf in BANNED_CALLS or called in BANNED_UNSAFE_DESERIALIZATION:
                raise CoreSafetyViolation(
                    f"{filename}:{node.lineno}: privileged call {called} prohibited"
                )
            if called in BANNED_BUILTINS or called in {
                "builtins.eval", "builtins.exec", "builtins.__import__",
            }:
                raise CoreSafetyViolation(
                    f"{filename}:{node.lineno}: dynamic code execution prohibited"
                )
            if called in {"importlib.import_module", "import_module"}:
                if node.args and isinstance(node.args[0], ast.Constant):
                    value = node.args[0].value
                    if isinstance(value, str) and value.split(".")[0] in BANNED_MODULES:
                        raise CoreSafetyViolation(
                            f"{filename}:{node.lineno}: dynamic broker import prohibited"
                        )


def scan_core(root: Path = CORE) -> int:
    if not root.is_dir():
        raise CoreSafetyViolation("First-party source directory missing")
    scripts = sorted(root.rglob("*.py"))
    if not scripts:
        raise CoreSafetyViolation("First-party source is empty")
    for file in scripts:
        if file.is_symlink():
            raise CoreSafetyViolation("Symlink forbidden under first-party source")
        check_code(file.read_text(encoding="utf-8"), filename=str(file.relative_to(root)))
    return len(scripts)


def check_env_defaults(example: str) -> None:
    pairs = {}
    for line in example.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise CoreSafetyViolation("Malformed environment example")
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise CoreSafetyViolation("Invalid environment setting name")
        if key in pairs:
            raise CoreSafetyViolation("Duplicate environment setting")
        pairs[key] = value.strip().strip("'\"")
    if pairs.get("GOLD_ALLOW_LIVE") != "false":
        raise CoreSafetyViolation("Live trading must default to false")
    if pairs.get("GOLD_EXECUTION_ENABLED") != "false":
        raise CoreSafetyViolation("Order execution must default to false")
    if pairs.get("GOLD_TRADING_MODE") != "paper":
        raise CoreSafetyViolation("Default trading mode must remain paper")


if __name__ == "__main__":
    count = scan_core()
    check_env_defaults((ROOT / ".env.example").read_text(encoding="utf-8"))
    print(f"PASS: {count} first-party Python files forbid direct broker order calls")
