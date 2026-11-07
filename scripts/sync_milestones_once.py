"""One-time, idempotent GitHub milestone synchronization for the existing 52 Issues.

Read-only default; requires a reviewed GitHub Actions job and --confirm.
Never closes/creates task issues, changes body/labels, or sets due dates.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "iitij/Gold-Intelligence-AI"
MARKER = re.compile(r"<!-- GOLD-TASK-ID:(P\d{2}-\d{2}) -->")


def gh(path: str, *, method: str = "GET", payload: dict | None = None):
    argv = ["gh", "api", "--method", method, path]
    kwargs: dict = {"capture_output": True, "text": True, "check": True, "timeout": 35}
    if payload is not None:
        argv += ["--input", "-"]
        kwargs["input"] = json.dumps(payload, ensure_ascii=False)
    return json.loads(subprocess.run(argv, **kwargs).stdout)


def pages(endpoint: str) -> list[dict]:
    items = []
    page = 1
    while True:
        part = gh(endpoint + ("&" if "?" in endpoint else "?") +
                  f"per_page=100&page={page}")
        if not isinstance(part, list):
            raise RuntimeError("GitHub API did not return a list")
        items.extend(part)
        if len(part) < 100:
            return items
        page += 1


def expected() -> tuple[dict, dict]:
    plan = json.loads((ROOT / "planning/backlog.json").read_text(encoding="utf-8"))
    phases = {p["id"]: p for p in plan["phases"]}
    tasks = {t["id"]: t for t in plan["tasks"]}
    if len(phases) != 12 or len(tasks) != 52:
        raise ValueError("Unexpected scope; review plan before migration")
    if any(t["phase"] not in phases for t in tasks.values()):
        raise ValueError("Task phase missing")
    return phases, tasks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    opts = parser.add_mutually_exclusive_group(required=True)
    opts.add_argument("--dry-run", action="store_true")
    opts.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    phases, tasks = expected()
    if args.dry_run:
        print("DRY RUN:", len(phases), "phase milestones and", len(tasks),
              "existing tasks; no GitHub calls")
        return
    if os.environ.get("GITHUB_REPOSITORY") != REPO or os.environ.get(
        "GITHUB_REF"
    ) != "refs/heads/main" or not os.environ.get("GH_TOKEN"):
        raise SystemExit("Authorized main-branch GitHub Actions token required")
    if shutil.which("gh") is None:
        raise SystemExit("GitHub CLI missing")
    metadata = gh("repos/" + REPO)
    if metadata.get("private") is not True:
        raise SystemExit("Repository must remain private")
    issues = {}
    for raw in pages("repos/" + REPO + "/issues?state=all"):
        if "pull_request" in raw:
            continue
        m = MARKER.search(raw.get("body") or "")
        if m:
            if m.group(1) in issues:
                raise SystemExit("Duplicate stable task marker")
            issues[m.group(1)] = raw
    if set(issues) != set(tasks):
        raise SystemExit("Issue/task mismatch; refusing partial migration")
    current = {x["title"]: x for x in pages("repos/" + REPO +
                                            "/milestones?state=all")}
    created = 0
    linked = 0
    skipped = 0
    for phase in phases.values():
        name = phase["id"] + " — " + phase["title"]
        if name not in current:
            current[name] = gh("repos/" + REPO + "/milestones", method="POST",
                               payload={"title": name, "description": phase["en"]})
            created += 1
    for tid, task in tasks.items():
        issue = issues[tid]
        phase = phases[task["phase"]]
        milestone = current[phase["id"] + " — " + phase["title"]]["number"]
        existing = issue.get("milestone")
        if existing is not None:
            if existing.get("number") != milestone:
                raise SystemExit("Task has conflicting manually assigned milestone")
            skipped += 1
            continue
        gh("repos/" + REPO + "/issues/" + str(issue["number"]),
           method="PATCH", payload={"milestone": milestone})
        linked += 1
    print(f"PASS: created {created} milestones, linked {linked} Issues, "
          f"already set {skipped}; no duplicate tasks")


if __name__ == "__main__":
    main()
