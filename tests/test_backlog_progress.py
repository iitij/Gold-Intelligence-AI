"""Do not overstate completion, and maintain JSON/CSV task status parity."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_csv_status_matches_canonical_json():
    data = json.loads((ROOT / "planning/backlog.json").read_text(encoding="utf-8"))
    with (ROOT / "planning/backlog.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == len(data["tasks"]) == 52
    indexed = {task["id"]: task for task in data["tasks"]}
    assert len({row["id"] for row in rows}) == len(rows)
    for row in rows:
        assert row["id"] in indexed
        assert row["status"] == indexed[row["id"]]["status"]


def test_incomplete_tasks_never_claim_done():
    data = json.loads((ROOT / "planning/backlog.json").read_text(encoding="utf-8"))
    assert not any(t["status"] == "done" for t in data["tasks"])
    partial = [t for t in data["tasks"] if t["status"] != "todo"]
    assert partial
    assert all(t["evidence"] for t in partial)
    blocked = [t for t in partial if t["status"] == "blocked"]
    assert blocked and all(t.get("blocked_reason") for t in blocked)


def test_training_still_blocked_even_after_partial_progress():
    data = json.loads((ROOT / "planning/backlog.json").read_text(encoding="utf-8"))
    for item_id in ("P03-01", "P05-01", "P05-02", "P05-03", "P08-04"):
        task = next(t for t in data["tasks"] if t["id"] == item_id)
        assert task["status"] == "todo"
