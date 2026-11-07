"""Summarize actual backlog status and unresolved evidence without GitHub access."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    plan = json.loads((ROOT / "planning/backlog.json").read_text(encoding="utf-8"))
    summary = Counter(t["status"] for t in plan["tasks"])
    print("Backlog:", len(plan["tasks"]), "tasks,", len(plan["phases"]), "phases")
    for status in ("todo", "in_progress", "blocked", "review", "done"):
        print(f"{status}: {summary[status]}")
    for task in plan["tasks"]:
        if task["status"] in ("blocked", "review"):
            print(task["id"], task["status"], "-", task.get("blocked_reason") or
                  "Awaiting explicit acceptance evidence")


if __name__ == "__main__":
    main()
