"""Supervised early-exit research baseline with episode-separated temporal splits."""
import argparse
import bisect
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import catboost
import lightgbm
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from replay_m15_reversal import BAR, first_quote, read_ticks

from goldintel.research.exits import simulate_exit

FEATURES = ["elapsed_seconds", "pnl", "spread", "price_change_from_entry"]
CUTOFF = datetime.fromisoformat("2026-11-13T00:00:00+00:00")


def episode_split(entry_time, terminal_time, cutoff=CUTOFF):
    """Purge episodes whose terminal label is not strictly before the cutoff."""
    return "train" if terminal_time < cutoff else "test" if entry_time >= cutoff else "purged"


def build_episodes(buckets):
    episodes = []
    exclusions = Counter()
    for decision in sorted(buckets):
        recent, prior = buckets.get(decision - BAR), buckets.get(decision - 2 * BAR)
        entry = first_quote(buckets, decision, 0)
        if not recent or not prior or not entry:
            exclusions["missing_entry_or_history"] += 1
            continue
        if decision - recent[-1][0] > timedelta(seconds=30) or decision - BAR - prior[-1][0] > timedelta(seconds=30):
            exclusions["stale_history"] += 1
            continue
        side = "short" if recent[-1][1] > prior[-1][1] else "long"
        price = entry[1] if side == "short" else entry[2]
        path = [q for boundary in (decision, decision + BAR) for q in buckets.get(boundary, ())
                if q[0] >= entry[0]]
        terminal = simulate_exit(
            path, side=side, entry_time=entry[0], entry_price=price,
            deadline=decision + BAR, stop_distance=None, target_distance=None,
            max_gap=timedelta(seconds=30),
        )
        if terminal.reason != "deadline":
            exclusions[terminal.reason] += 1
            continue
        times = [q[0] for q in path]
        observations = []
        sign = Decimal(-1) if side == "short" else Decimal(1)
        for seconds in range(0, 900, 30):
            index = bisect.bisect_left(times, entry[0] + timedelta(seconds=seconds))
            if index >= len(path) or path[index][0] >= terminal.time:
                break
            time, bid, ask = path[index]
            liquidation = ask if side == "short" else bid
            pnl = sign * (liquidation - price)
            observations.append({
                "time": time.isoformat(), "elapsed_seconds": (time - entry[0]).total_seconds(),
                "pnl": float(pnl), "spread": float(ask - bid),
                "price_change_from_entry": float(bid - entry[1]),
                "exit_better_than_terminal": int(pnl >= terminal.gross_usd_per_ounce),
            })
        episodes.append({
            "entry_time": entry[0].isoformat(), "terminal_time": terminal.time.isoformat(),
            "terminal_pnl": float(terminal.gross_usd_per_ounce),
            "split": episode_split(entry[0], terminal.time),
            "observations": observations,
        })
    return episodes, dict(exclusions)


def select_exit(episode, probabilities):
    """Execute the first threshold crossing; terminal labels cannot affect selection."""
    if len(probabilities) != len(episode["observations"]):
        raise ValueError("Prediction count must match causal observations")
    if any(not np.isfinite(value) or not 0 <= value <= 1 for value in probabilities):
        raise ValueError("Invalid exit probabilities")
    selected = next((row for row, value in zip(episode["observations"], probabilities)
                     if value >= .5), None)
    return {
        "entry_time": episode["entry_time"], "terminal_pnl": episode["terminal_pnl"],
        "policy_pnl": selected["pnl"] if selected else episode["terminal_pnl"],
        "exit_time": selected["time"] if selected else episode["terminal_time"],
        "immediate_pnl": episode["observations"][0]["pnl"],
        "exit_reason": "threshold" if selected else "deadline",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("quotes", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh output directory")
    buckets = read_ticks(args.quotes, preserve_all=True)
    episodes, exclusions = build_episodes(buckets)
    training = pd.DataFrame([row for episode in episodes if episode["split"] == "train"
                             for row in episode["observations"]])
    testing = [episode for episode in episodes if episode["split"] == "test"]
    if training.empty or not testing or training.exit_better_than_terminal.nunique() != 2:
        raise ValueError("Training needs both classes and a nonempty later evaluation period")
    args.output.mkdir()
    models = {
        "LightGBM": LGBMClassifier(n_estimators=100, max_depth=3, num_leaves=8,
                                   n_jobs=2, random_state=42, verbosity=-1),
        "CatBoost": CatBoostClassifier(iterations=100, depth=3, thread_count=2,
                                       random_seed=42, verbose=False, allow_writing_files=False),
    }
    report = {
        "input_sha256": hashlib.sha256(args.quotes.read_bytes()).hexdigest(),
        "features": FEATURES, "train_rows": len(training), "test_episodes": len(testing),
        "episode_counts": dict(Counter(e["split"] for e in episodes)),
        "excluded_episode_counts": exclusions,
        "train_class_counts": {str(k): int(v) for k, v in training.exit_better_than_terminal.value_counts().items()},
        "episode_windows": {
            split: {"first_entry": min(e["entry_time"] for e in episodes if e["split"] == split),
                    "last_terminal": max(e["terminal_time"] for e in episodes if e["split"] == split)}
            for split in ("train", "test")
        },
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "versions": {"lightgbm": lightgbm.__version__, "catboost": catboost.__version__,
                     "pandas": pd.__version__, "numpy": np.__version__},
        "split_cutoff_encoded_native": CUTOFF.isoformat(), "models": {},
        "approved_for_trading": False,
        "baselines": {
            "no_trade_mean_pnl": 0.0,
            "immediate_exit_mean_pnl": float(np.mean([e["observations"][0]["pnl"] for e in testing])),
            "terminal_mean_pnl": float(np.mean([e["terminal_pnl"] for e in testing])),
        },
        "limitations": ["Provisional UTC encoding of native chronology", "Previously inspected diagnostic dates",
                        "Supervised exit labels compare immediate versus terminal liquidation",
                        "Commission and additional slippage excluded", "Unknown terminal exits excluded",
                        "Independent episodes, not an executable single-position portfolio",
                        "Zero-latency threshold exits are optimistic; immediate exits pay the observed spread",
                        "One later diagnostic day cannot establish robustness or a confidence interval",
                        "Supervised comparison against a fixed terminal policy, not reinforcement learning"],
    }
    for name, model in models.items():
        model.fit(training[FEATURES], training.exit_better_than_terminal)
        model_path = args.output / ("lightgbm-exit.txt" if name == "LightGBM" else "catboost-exit.cbm")
        if name == "LightGBM":
            model.booster_.save_model(str(model_path))
            restored = lightgbm.Booster(model_file=str(model_path))
        else:
            model.save_model(str(model_path))
            restored = CatBoostClassifier().load_model(str(model_path))
        ledger = []
        max_reload_error = 0.0
        for episode in testing:
            rows = pd.DataFrame(episode["observations"])
            probability = model.predict_proba(rows[FEATURES])[:, 1]
            restored_probability = (restored.predict(rows[FEATURES], num_threads=2) if name == "LightGBM"
                                    else restored.predict_proba(rows[FEATURES])[:, 1])
            error = float(np.max(np.abs(probability - restored_probability)))
            max_reload_error = max(max_reload_error, error)
            if error > 1e-12:
                raise ValueError("Saved model failed prediction reproduction")
            ledger.append(select_exit(episode, restored_probability))
        report["models"][name] = {
            "mean_policy_pnl": sum(t["policy_pnl"] for t in ledger) / len(ledger),
            "mean_terminal_pnl": sum(t["terminal_pnl"] for t in ledger) / len(ledger),
            "immediate_exit_count": sum(t["exit_time"] == t["entry_time"] for t in ledger),
            "mean_above_no_trade": sum(t["policy_pnl"] for t in ledger) > 0,
            "matches_immediate_exit_baseline": all(t["policy_pnl"] == t["immediate_pnl"] for t in ledger),
            "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
            "parameters": model.get_params(), "max_reload_probability_error": max_reload_error,
            "ledger": ledger,
        }
    (args.output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
