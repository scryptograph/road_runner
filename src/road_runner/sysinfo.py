"""System information collection."""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path
from typing import Dict


def _run_command(args: list[str]) -> str:
    try:
        result = subprocess.run(
            args,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        return "command-not-found"
    if result.returncode != 0:
        return f"error({result.returncode}): {result.stderr.strip()}"
    return result.stdout.strip()


def _read_optional(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "file-not-found"
    except PermissionError:
        return "permission-denied"


def collect_sysinfo() -> Dict[str, str]:
    info: Dict[str, str] = {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
    }
    info["uname"] = _run_command(["uname", "-a"])
    info["lscpu"] = _run_command(["lscpu"])
    info["dmidecode"] = _run_command(["dmidecode"])
    if shutil.which("sensors"):
        info["sensors"] = _run_command(["sensors"])
    else:
        info["sensors"] = "sensors-not-available"
    info["meminfo"] = _read_optional(Path("/proc/meminfo"))
    info["cpuinfo"] = _read_optional(Path("/proc/cpuinfo"))
    return info
