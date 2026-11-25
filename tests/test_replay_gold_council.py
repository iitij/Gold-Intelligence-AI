"""Council input loading must happen after the prospective-window gate."""

import sys
from datetime import datetime
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest

from goldintel.research.holdout import HoldoutError


def test_sealed_council_request_never_loads_evidence(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    council = import_module("replay_gold_council")
    now = datetime.fromisoformat("2026-11-25T15:10:00+00:00")
    monkeypatch.setattr(council, "datetime", SimpleNamespace(now=lambda _: now))
    snapshot = tmp_path / "snapshot.json"
    output = tmp_path / "result.json"

    def unexpected(*args):
        pytest.fail("Council tried to load evidence before checking the holdout")

    monkeypatch.setattr(council, "load_tools", unexpected)
    monkeypatch.setattr(sys, "argv", ["replay_gold_council.py", "--snapshot", str(snapshot),
                                      "--snapshot-id", "f" * 64, "--as-of", "2026-11-24T00:00:00Z",
                                      "--output", str(output)])
    with pytest.raises(HoldoutError, match="overlaps a sealed registered holdout"):
        council.main()
    assert not output.exists()
