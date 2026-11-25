"""Causal observation and episode-boundary checks for the supervised exit diagnostic."""
import importlib.util
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("pandas")
pytest.importorskip("lightgbm")
pytest.importorskip("catboost")


@pytest.fixture
def policy(monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("exit_training", scripts / "train_quote_exit_policy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_training_labels_strictly_precede_later_episodes(policy):
    cutoff = policy.CUTOFF
    assert policy.episode_split(cutoff - policy.BAR, cutoff) == "purged"
    assert policy.episode_split(cutoff - policy.BAR, cutoff - timedelta(microseconds=1)) == "train"
    assert policy.episode_split(cutoff, cutoff + policy.BAR) == "test"


def test_future_quote_changes_labels_but_not_earlier_features(policy):
    decision = policy.CUTOFF
    buckets = {}
    for offset in range(-2, 2):
        start = decision + offset * policy.BAR
        buckets[start] = [
            (start + timedelta(seconds=s), Decimal("100"), Decimal("101"))
            for s in range(0, 900, 30)
        ]
    original, _ = policy.build_episodes(buckets)
    changed = deepcopy(buckets)
    changed[decision + policy.BAR] = [
        (time, bid + 10, ask + 10) for time, bid, ask in changed[decision + policy.BAR]
    ]
    modified, _ = policy.build_episodes(changed)
    before = next(e for e in original if e["entry_time"] == decision.isoformat())
    after = next(e for e in modified if e["entry_time"] == decision.isoformat())
    assert before["terminal_pnl"] != after["terminal_pnl"]
    assert [o["exit_better_than_terminal"] for o in before["observations"]] != [
        o["exit_better_than_terminal"] for o in after["observations"]
    ]
    for left, right in zip(before["observations"], after["observations"]):
        assert {key: left[key] for key in policy.FEATURES} == {
            key: right[key] for key in policy.FEATURES
        }
    probabilities = [0.6] * len(before["observations"])
    exit_before = policy.select_exit(before, probabilities)
    exit_after = policy.select_exit(after, probabilities)
    assert exit_before["policy_pnl"] == exit_after["policy_pnl"] == -1
    assert exit_before["exit_time"] == exit_after["exit_time"] == decision.isoformat()


def test_exit_selection_uses_first_crossing_and_terminal_fallback(policy):
    episode = {
        "entry_time": "entry", "terminal_time": "end", "terminal_pnl": 99,
        "observations": [{"time": "first", "pnl": -1}, {"time": "second", "pnl": 2}],
    }
    assert policy.select_exit(episode, [0.5, 0.9])["policy_pnl"] == -1
    assert policy.select_exit(episode, [0.4, 0.5])["exit_time"] == "second"
    assert policy.select_exit(episode, [0.4, 0.4])["policy_pnl"] == 99
    with pytest.raises(ValueError, match="count"):
        policy.select_exit(episode, [0.5])
    with pytest.raises(ValueError, match="probabilities"):
        policy.select_exit(episode, [float("nan"), 0.5])
