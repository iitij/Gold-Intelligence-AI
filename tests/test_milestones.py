"""Offline tests of one-time milestone scope; never contact GitHub in CI."""
import subprocess
import sys
from pathlib import Path

from scripts.sync_milestones_once import expected

ROOT = Path(__file__).resolve().parents[1]


def test_milestone_plan_matches_stable_52_issue_inventory():
    phases, tasks = expected()
    assert len(phases) == 12
    assert len(tasks) == 52
    assert all(t["phase"] in phases for t in tasks.values())


def test_sync_has_no_network_by_default():
    result = subprocess.run([sys.executable, "scripts/sync_milestones_once.py", "--dry-run"],
                            cwd=ROOT, check=True, capture_output=True, text=True)
    assert "no GitHub calls" in result.stdout


def test_no_unapproved_local_token_mutation():
    result = subprocess.run([sys.executable, "scripts/sync_milestones_once.py", "--confirm"],
                            cwd=ROOT, check=False, capture_output=True, text=True,
                            env={"PATH": "/usr/bin:/bin"})
    assert result.returncode != 0
    assert "Authorized main-branch" in result.stderr
