"""Safe workstation inventory for research planning, no broker or personal details.

Reports only CPU model, RAM, free disk, OS distribution, Python/Wine versions,
GPU model and VRAM. Never captures serials, hostname, usernames, paths,
MetaTrader login credentials, account numbers, IP addresses or running processes.
Run locally on the owner's Ubuntu workstation, not in GitHub Actions.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def _run(*argv: str) -> str | None:
    if shutil.which(argv[0]) is None:
        return None
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def inventory() -> dict:
    cpu = "unknown"
    if Path("/proc/cpuinfo").is_file():
        for line in Path("/proc/cpuinfo").read_text(errors="replace").splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    mem_gib = None
    if Path("/proc/meminfo").is_file():
        first = Path("/proc/meminfo").read_text().splitlines()[0]
        if first.startswith("MemTotal:"):
            mem_gib = round(int(first.split()[1]) / (1024 ** 2), 2)
    disk_gib = round(shutil.disk_usage(Path.home()).free / (1024 ** 3), 1)
    gpu = _run("nvidia-smi", "--query-gpu=name,memory.total",
               "--format=csv,noheader,nounits")
    wine = _run("wine", "--version")
    return {
        "schema_version": 1,
        "scope": "local_hardware_only_no_broker_account_information",
        "os": platform.system(),
        "cpu_model": cpu,
        "logical_cores": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity")
                         else (os.cpu_count() or 0),
        "ram_gib": mem_gib,
        "disk_free_gib": disk_gib,
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "wine_version": wine or "unavailable",
        "nvidia_gpu": gpu or "unavailable",
        "source": "observed_on_user_workstation_only",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="local ignored folder only")
    args = parser.parse_args()
    report = inventory()
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        resolved = args.output.resolve()
        allowed = (Path.cwd() / ".local").resolve()
        if not resolved.is_relative_to(allowed):
            parser.error("Output must stay inside ignored .local/ folder")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(payload, encoding="utf-8")
        print("Local inventory saved to ignored .local/; do not commit.")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
