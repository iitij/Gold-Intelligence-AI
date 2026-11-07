"""Idempotent GitHub issue/label/milestone synchronizer for EXISTING private repo.

Dry-run default. Never edits issue title/body/state or deletes anything.
With --confirm, create missing milestones and labels, then create missing issues
and attach labels/milestones to existing tasks identified by a stable marker.
Requires authenticated GitHub CLI (gh) on the owner's machine.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def gh(*args, data=None):
    cmd = ["gh", *args]
    kwargs = dict(text=True, check=True, capture_output=True)
    if data is not None:
        kwargs["input"] = json.dumps(data, ensure_ascii=False)
    result = subprocess.run(cmd, **kwargs)
    return json.loads(result.stdout) if result.stdout.strip() else None


def api(path, data=None):
    if data is not None:
        return gh("api", "-X", "POST", path, "--input", "-", data=data)
    return gh("api", path)


def pages(path):
    return gh("api", "--paginate", "--slurp", path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="iitij/Gold-Intelligence-AI")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    backlog = json.loads((ROOT / "planning/backlog.json").read_text(encoding="utf-8"))
    ids = {t["id"] for t in backlog["tasks"]}
    if len(ids) != len(backlog["tasks"]):
        raise SystemExit("Duplicate backlog IDs")
    if not all(set(t["depends_on"]) <= ids for t in backlog["tasks"]):
        raise SystemExit("Unknown dependencies")
    if args.dry_run:
        print("DRY RUN:", args.repo, len(backlog["phases"]), "phases;",
              len(backlog["tasks"]), "issues")
        return
    if args.repo != "iitij/Gold-Intelligence-AI":
        raise SystemExit("Only the explicitly authorized repository is supported")
    if not shutil.which("gh"):
        raise SystemExit("Install and authenticate GitHub CLI first")
    repository = api("repos/" + args.repo)
    if not repository.get("private"):
        raise SystemExit("Repository must remain private")
    existing_issues = [
        issue for page in pages("repos/" + args.repo + "/issues?state=all&per_page=100")
        for issue in page if "pull_request" not in issue
    ]
    by_id = {}
    for issue in existing_issues:
        marker = (issue.get("body") or "").split("<!-- GOLD-TASK-ID:")
        if len(marker) > 1:
            by_id[marker[1].split("-->")[0].strip()] = issue
    existing_milestones = {
        m["title"]: m["number"]
        for page in pages("repos/" + args.repo + "/milestones?state=all&per_page=100")
        for m in page
    }
    for phase in backlog["phases"]:
        title = phase["id"] + " — " + phase["title"]
        if title not in existing_milestones:
            m = api("repos/" + args.repo + "/milestones", {
                "title": title, "description": phase["en"],
            })
            existing_milestones[title] = m["number"]
    label_names = {
        label["name"]
        for page in pages("repos/" + args.repo + "/labels?per_page=100")
        for label in page
    }
    needed = {label for task in backlog["tasks"] for label in task["labels"]}
    for name in sorted(needed - label_names):
        api("repos/" + args.repo + "/labels", {
            "name": name, "color": "677788", "description": "Gold Intelligence AI task tag",
        })
    for task in backlog["tasks"]:
        phase = next(p for p in backlog["phases"] if p["id"] == task["phase"])
        milestone = existing_milestones[phase["id"] + " — " + phase["title"]]
        issue = by_id.get(task["id"])
        if issue is not None:
            # Preserve manually added labels, state, title and issue body.
            existing_labels = {label["name"] for label in issue.get("labels", [])}
            missing = set(task["labels"]) - existing_labels
            if missing:
                api("repos/" + args.repo + "/issues/" + str(issue["number"]) + "/labels",
                    {"labels": sorted(missing)})
            if issue.get("milestone") is None:
                gh("api", "-X", "PATCH",
                   "repos/" + args.repo + "/issues/" + str(issue["number"]),
                   "--input", "-", data={"milestone": milestone})
            continue
        body = "\n".join([
            "<!-- GOLD-TASK-ID:" + task["id"] + " -->",
            "## الهدف", task["goal"], "## شروط القبول",
            *("- [ ] " + item for item in task["acceptance"]),
            "## يعتمد على", ", ".join(task["depends_on"]) or "لا يوجد",
            "## الدليل المطلوب", "PR + checks + documented acceptance decision",
        ])
        api("repos/" + args.repo + "/issues", {
            "title": "[" + task["id"] + "] " + task["title"],
            "body": body, "labels": task["labels"], "milestone": milestone,
        })
    print("DONE. Backlog aligned; no duplicate task IDs created.")


if __name__ == "__main__":
    main()
