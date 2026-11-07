import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load():
    return json.loads((ROOT / "planning/backlog.json").read_text(encoding="utf-8"))


def test_backlog_is_unique_and_a_complete_dag():
    data = load()
    ids = {task["id"] for task in data["tasks"]}
    assert len(ids) == len(data["tasks"])
    assert len(data["tasks"]) >= 40
    assert {p["id"] for p in data["phases"]} == {t["phase"] for t in data["tasks"]}
    graph = {t["id"]: t["depends_on"] for t in data["tasks"]}
    for task in data["tasks"]:
        assert task["id"].startswith(task["phase"] + "-")
        assert task["goal"].strip()
        assert all(s.strip() for s in task["acceptance"])
        assert all(dep in ids for dep in task["depends_on"])

    visiting, visited = set(), set()

    def visit(node):
        assert node not in visiting, "cycle in task dependencies"
        if node in visited:
            return
        visiting.add(node)
        for dep in graph[node]:
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def test_project_scope_and_release_gates():
    data = load()
    assert data["scope"] == "XAUUSD only"
    assert all(t["status"] in data["workflow"] for t in data["tasks"])
    ids = {t["id"] for t in data["tasks"]}
    for mandatory in (
        "P00-02", "P01-02", "P01-03", "P05-02",
        "P07-02", "P08-04", "P09-04", "P10-04",
    ):
        assert mandatory in ids


def test_docs_and_source_policies_exist():
    for path in (
        "docs/00-CHARTER.md", "docs/01-ARCHITECTURE.md",
        "docs/03-TRAINING-STRATEGY.md", "docs/05-STRATEGIES.md",
        "docs/08-SECURITY-OPERATIONS.md", "docs/10-LICENSING.md",
        "docs/12-PUBLISHING.md", "sources/sources.lock.json",
        "models/model_catalog.json", "planning/ROADMAP.md",
    ):
        assert (ROOT / path).is_file(), path
