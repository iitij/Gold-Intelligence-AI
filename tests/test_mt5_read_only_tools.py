"""Keep the broker-facing quote collectors on the read-only MT5 API."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
READ_ONLY_METHODS = {
    "initialize", "shutdown", "account_info", "last_error",
    "copy_ticks_range", "symbol_info_tick", "terminal_info", "copy_rates_from_pos",
}


@pytest.mark.parametrize("name", [
    "export_headway_ticks.py", "observe_headway_clock.py", "capture_headway_quote.py",
    "capture_headway_market_inputs.py",
])
def test_python_collectors_use_read_only_mt5_methods(name):
    tree = ast.parse((ROOT / "scripts" / name).read_text())
    methods = {
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name) and node.func.value.id == "mt5"
    }
    assert methods
    assert methods <= READ_ONLY_METHODS


def test_native_tick_export_has_no_order_api():
    source = (ROOT / "mt5/ExportXAUUSD_Ticks.mq5").read_text()
    assert "CopyTicksRange(" in source
    for identifier in ("OrderSend", "CTrade", "TRADE_ACTION_"):
        assert identifier not in source
