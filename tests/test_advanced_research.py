"""P11 research extension must remain dependency-safe and explicitly paper-only."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_advanced_research_tasks_declared_once():
    plan = json.loads((ROOT / "planning/backlog.json").read_text(encoding="utf-8"))
    tasks = {t["id"]: t for t in plan["tasks"]}
    advanced = {f"P11-0{i}" for i in range(1, 5)}
    assert advanced.issubset(tasks)
    assert len(plan["tasks"]) == 52
    assert len(plan["phases"]) == 12
    for task_id in advanced:
        assert tasks[task_id]["status"] == "todo"
        assert tasks[task_id]["depends_on"]
        assert all(tasks[task_id]["acceptance"])


def test_tournament_preserves_no_trade_and_heldout_evidence():
    plan = json.loads((ROOT / "planning/backlog.json").read_text(encoding="utf-8"))
    tournament = next(x for x in plan["tasks"] if x["id"] == "P11-01")
    text = " ".join(tournament["acceptance"])
    assert "Holdout" in text
    assert "Net-Expectancy" in text
    assert "Ablation" in text
