"""Configuration loaders for flows, margins, and safety policy."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from .exceptions import ValidationError
from .models import Bound, FlowDefinition, FlowStep, MarginProfile, SafetyPolicy, TargetMargins
from .utils import load_yaml


def _require_keys(data: Dict[str, Any], keys: Sequence[str], context: str) -> None:
    for key in keys:
        if key not in data:
            raise ValidationError(f"{context}: missing required key '{key}'")


def load_flow(path: Path) -> FlowDefinition:
    payload = load_yaml(path)
    if not isinstance(payload, dict):
        raise ValidationError(f"{path}: expected mapping at root")
    _require_keys(payload, ("metadata", "steps"), f"{path}")

    metadata = payload["metadata"]
    steps_raw = payload["steps"]
    if not isinstance(steps_raw, list):
        raise ValidationError(f"{path}: 'steps' must be a list")

    steps: List[FlowStep] = []
    for idx, entry in enumerate(steps_raw):
        if not isinstance(entry, dict):
            raise ValidationError(f"{path}: step[{idx}] must be a mapping")
        _require_keys(entry, ("name", "adapter"), f"{path} step[{idx}]")
        parameters = entry.get("parameters", {})
        sweeps = entry.get("sweeps", {})
        if not isinstance(parameters, dict):
            raise ValidationError(f"{path} step[{idx}]: parameters must be mapping")
        if sweeps and not isinstance(sweeps, dict):
            raise ValidationError(f"{path} step[{idx}]: sweeps must be mapping")
        normalized_sweeps = {}
        for sweep_key, sweep_values in (sweeps or {}).items():
            if not isinstance(sweep_values, Iterable) or isinstance(sweep_values, (str, bytes)):
                raise ValidationError(
                    f"{path} step[{idx}]: sweep '{sweep_key}' must be iterable of values"
                )
            normalized_sweeps[sweep_key] = list(sweep_values)
        steps.append(
            FlowStep(
                name=str(entry["name"]),
                adapter=str(entry["adapter"]),
                parameters=dict(parameters),
                sweeps=normalized_sweeps,
            )
        )

    return FlowDefinition(metadata=dict(metadata), steps=steps)


def load_margin_profile(path: Path) -> MarginProfile:
    payload = load_yaml(path)
    if not isinstance(payload, dict):
        raise ValidationError(f"{path}: expected mapping at root")
    _require_keys(payload, ("metadata", "targets"), f"{path}")
    metadata = payload["metadata"]
    targets_raw = payload["targets"]
    if not isinstance(targets_raw, dict):
        raise ValidationError(f"{path}: 'targets' must be a map")

    targets: Dict[str, TargetMargins] = {}
    for target_name, target_payload in targets_raw.items():
        if not isinstance(target_payload, dict):
            raise ValidationError(f"{path} target '{target_name}' must be mapping")
        fixed: Dict[str, Any] = {}
        sweeps: Dict[str, Sequence[Any]] = {}
        jitter = None

        for param_name, value in target_payload.items():
            if param_name == "jitter":
                jitter = value if isinstance(value, dict) else None
                continue
            if isinstance(value, dict):
                if "sweep" in value:
                    sweep_values = value["sweep"]
                    if not isinstance(sweep_values, Iterable) or isinstance(
                        sweep_values, (str, bytes)
                    ):
                        raise ValidationError(
                            f"{path} target '{target_name}' sweep '{param_name}' must be list-like"
                        )
                    sweeps[param_name] = list(sweep_values)
                elif "value" in value:
                    fixed[param_name] = value["value"]
                else:
                    fixed[param_name] = value
            else:
                fixed[param_name] = value

        targets[target_name] = TargetMargins(fixed=fixed, sweeps=sweeps, jitter=jitter)

    seed = payload.get("global_seed")
    if seed is not None and not isinstance(seed, int):
        raise ValidationError(f"{path}: global_seed must be integer")

    return MarginProfile(metadata=dict(metadata), global_seed=seed, targets=targets)


def parse_safety_policy(payload: Dict[str, Any], context: str) -> SafetyPolicy:
    _require_keys(payload, ("metadata", "avt_bounds"), context)

    bounds_raw = payload["avt_bounds"]
    if not isinstance(bounds_raw, dict):
        raise ValidationError(f"{context}: 'avt_bounds' must be a mapping")

    bounds = {}
    for name, entry in bounds_raw.items():
        if isinstance(entry, dict):
            bounds[name] = Bound(entry.get("min"), entry.get("max"))
        else:
            raise ValidationError(f"{context}: bound '{name}' must be mapping")

    behavior = payload.get("behavior", {})
    if behavior and not isinstance(behavior, dict):
        raise ValidationError(f"{context}: 'behavior' must be mapping when present")

    return SafetyPolicy(metadata=dict(payload["metadata"]), avt_bounds=bounds, behavior=behavior)


def load_safety_policy(path: Path) -> SafetyPolicy:
    payload = load_yaml(path)
    if not isinstance(payload, dict):
        raise ValidationError(f"{path}: expected mapping at root")
    return parse_safety_policy(payload, f"{path}")
