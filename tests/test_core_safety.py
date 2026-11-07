"""Broker privilege gate cannot be bypassed by optimization or text comments."""
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_core_safety import (
    CoreSafetyViolation,
    check_code,
    check_env_defaults,
    scan_core,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("source", [
    "import MetaTrader5\n",
    "from mt5linux import MetaTrader5\n",
    "mt5.order_send({'symbol':'XAUUSD'})\n",
    "order_send({'symbol':'XAUUSD'})\n",
    "client.OrderSend(request)\n",
    "importlib.import_module('MetaTrader5')\n",
    "pickle.loads(raw)\n",
    "eval('2+2')\n",
    "exec(payload)\n",
    "import builtins\nbuiltins.__import__('x')\n",
])
def test_rejects_privileged_code(source):
    with pytest.raises(CoreSafetyViolation):
        check_code(source)


def test_ast_ignores_comments_and_safe_words():
    check_code("# order_send() is prohibited\n")
    check_code("action='BUY'; permission=False\n")
    check_code("def calculate_risk(proposal): return proposal\n")


@pytest.mark.parametrize("invalid", [
    "GOLD_ALLOW_LIVE=true",
    "GOLD_ALLOW_LIVE=false\nGOLD_ALLOW_LIVE=true",
    "GOLD_EXECUTION_ENABLED=true",
    "GOLD_TRADING_MODE=live",
])
def test_env_security_defaults_cannot_be_weakened(invalid):
    baseline = (
        "GOLD_ALLOW_LIVE=false\n"
        "GOLD_EXECUTION_ENABLED=false\n"
        "GOLD_TRADING_MODE=paper\n"
    )
    with pytest.raises(CoreSafetyViolation):
        check_env_defaults(baseline + "\n" + invalid)


def test_default_core_is_read_only():
    assert scan_core() >= 10
    check_env_defaults((ROOT / ".env.example").read_text(encoding="utf-8"))


def test_policy_runs_even_with_python_optimization():
    proc = subprocess.run(
        [sys.executable, "-O", "scripts/check_repository_policy.py"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "fail-closed" in proc.stdout
