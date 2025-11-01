"""Utility helpers."""

from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def dump_json(data: Any, path: Path) -> None:
    if is_dataclass(data):
        data = asdict(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ensure_seed(seed: int | None) -> int:
    if seed is None:
        seed = int(time.time())
    random.seed(seed)
    return seed
