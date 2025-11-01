"""Artifact management utilities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .utils import dump_json


def timestamp_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", name.strip()).strip("-").lower()


@dataclass(slots=True)
class RunPaths:
    parent_id: str
    base_dir: Path

    @property
    def parent_dir(self) -> Path:
        return self.base_dir / self.parent_id

    @property
    def plan_path(self) -> Path:
        return self.parent_dir / "plan.json"

    @property
    def summary_path(self) -> Path:
        return self.parent_dir / "summary.json"

    @property
    def sysinfo_path(self) -> Path:
        return self.parent_dir / "sysinfo.json"

    @property
    def safety_policy_path(self) -> Path:
        return self.parent_dir / "safety_policy.json"

    @property
    def markdown_report_path(self) -> Path:
        return self.parent_dir / "report.md"

    @property
    def html_report_path(self) -> Path:
        return self.parent_dir / "report.html"

    def subrun_dir(self, subrun_id: str) -> Path:
        return self.parent_dir / "subruns" / subrun_id

    def subrun_summary(self, subrun_id: str) -> Path:
        return self.subrun_dir(subrun_id) / "summary.json"

    def subrun_ldjson(self, subrun_id: str) -> Path:
        return self.subrun_dir(subrun_id) / "steps.ldjson"

    def step_stdout(self, subrun_id: str, step_name: str, index: int, invocation: int) -> Path:
        suffix = f"{index:02d}_{sanitize(step_name)}"
        if invocation:
            suffix += f"_{invocation:02d}"
        return self.subrun_dir(subrun_id) / "stdout" / f"{suffix}.log"

    def step_stderr(self, subrun_id: str, step_name: str, index: int, invocation: int) -> Path:
        suffix = f"{index:02d}_{sanitize(step_name)}"
        if invocation:
            suffix += f"_{invocation:02d}"
        return self.subrun_dir(subrun_id) / "stderr" / f"{suffix}.log"


class LDJSONLogger:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: Dict[str, Any]) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record))
            handle.write("\n")


def write_summary(path: Path, payload: Dict[str, Any]) -> None:
    dump_json(payload, path)
