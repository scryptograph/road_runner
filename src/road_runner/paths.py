"""Shared project path helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = (
    Path(os.environ["ROAD_RUNNER_HOME"]).expanduser().resolve()
    if "ROAD_RUNNER_HOME" in os.environ
    else Path.cwd()
)


def flows_dir() -> Path:
    return PROJECT_ROOT / "flows"


def margins_dir() -> Path:
    return PROJECT_ROOT / "margins"


def policy_file() -> Path:
    return PROJECT_ROOT / "policy" / "safety.yaml"


def adapters_dir() -> Path:
    return PROJECT_ROOT / "adapters"


def diags_dir() -> Path:
    return PROJECT_ROOT / "diags"


def policy_profiles_dir() -> Path:
    return PROJECT_ROOT / "policy" / "profiles"


def runs_dir() -> Path:
    return PROJECT_ROOT / "runs"


def templates_dir() -> Path:
    return PROJECT_ROOT / "templates"
