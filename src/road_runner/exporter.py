"""Export utilities."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .artifacts import RunPaths
from .utils import read_json


def export_csv(parent_dir: Path, output_path: Path | None = None) -> Path:
    run_paths = RunPaths(parent_id=parent_dir.name, base_dir=parent_dir.parent)
    summary = read_json(run_paths.summary_path)
    subruns: Iterable[Dict[str, Any]] = summary.get("subruns", [])
    rows: List[Dict[str, Any]] = []

    for sub in subruns:
        for step in sub.get("steps", []):
            row = {
                "parent_run_id": summary["run_id"],
                "sub_run_id": sub["run_id"],
                "margin_point": sub["margin"]["point_id"],
                "step_name": step["name"],
                "status": step["status"],
                "duration_s": step["duration_s"],
            }
            rows.append(row)

    destination = output_path or parent_dir / f"{parent_dir.name}_export.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["parent_run_id", "sub_run_id", "margin_point", "step_name", "status", "duration_s"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return destination
