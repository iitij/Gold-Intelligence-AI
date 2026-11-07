"""Fail-closed readiness and local inventory tests; no broker access."""
import json
import subprocess
import sys
from pathlib import Path

from scripts.preflight import GateError, accepted_gates, check_goal, read_gates

ROOT = Path(__file__).resolve().parents[1]


def test_all_gates_present_and_blocked():
    data = read_gates()
    assert {g["id"] for g in data["gates"]} == {
        "G0", "G1", "G2", "G3", "G4", "G5", "G6"
    }
    assert not accepted_gates(data)
    for goal in ("training", "research-evaluation", "demo", "production"):
        allowed, missing = check_goal(data, goal)
        assert not allowed and missing


def test_readiness_never_automatically_enables_training():
    cp = subprocess.run([sys.executable, "scripts/preflight.py", "check", "training"],
                        cwd=ROOT, capture_output=True, text=True, check=False)
    assert cp.returncode == 2
    assert "BLOCKED" in cp.stderr


def test_empty_evidence_is_rejected(tmp_path):
    data = read_gates()
    data["gates"][0]["requirements"][0]["verified"] = True
    source = tmp_path / "bad.json"
    source.write_text(json.dumps(data))
    try:
        read_gates(source)
    except GateError:
        return
    raise AssertionError("Unproven verified item was accepted")


def test_requirement_deletion_cannot_bypass_gate(tmp_path):
    data = read_gates()
    data["gates"][0]["requirements"].pop()
    source = tmp_path / "bad.json"
    source.write_text(json.dumps(data))
    try:
        read_gates(source)
    except GateError:
        return
    raise AssertionError("Deleted requirement evaded gate")


def test_workstation_inventory_does_not_request_accounts():
    from scripts.local_inventory import inventory

    report = inventory()
    assert report["scope"] == "local_hardware_only_no_broker_account_information"
    for secret in ("hostname", "username", "account", "login", "password", "ip", "serial"):
        assert secret not in report.keys()


def test_inventory_must_write_inside_ignored_directory(tmp_path):
    cp = subprocess.run(
        [sys.executable, "scripts/local_inventory.py", "--output", str(tmp_path / "out.json")],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert cp.returncode != 0
    assert "ignored .local/" in cp.stderr
