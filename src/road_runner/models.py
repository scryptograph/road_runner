"""Data models for road_runner."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from .exceptions import SafetyViolationError, ValidationError


@dataclass(slots=True)
class FlowStep:
    name: str
    adapter: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    sweeps: Dict[str, Sequence[Any]] = field(default_factory=dict)

    def expanded_parameters(self) -> Iterable[Dict[str, Any]]:
        if not self.sweeps:
            yield dict(self.parameters)
            return
        keys = list(self.sweeps.keys())
        combos = itertools.product(*(self.sweeps[key] for key in keys))
        for combo in combos:
            params = dict(self.parameters)
            params.update(dict(zip(keys, combo)))
            yield params


@dataclass(slots=True)
class FlowDefinition:
    metadata: Mapping[str, Any]
    steps: List[FlowStep]


@dataclass(slots=True)
class TargetMargins:
    fixed: Dict[str, Any] = field(default_factory=dict)
    sweeps: Dict[str, Sequence[Any]] = field(default_factory=dict)
    jitter: Mapping[str, Any] | None = None


@dataclass(slots=True)
class MarginPoint:
    identifier: str
    values: Dict[str, Dict[str, Any]]
    seed: int


@dataclass(slots=True)
class MarginProfile:
    metadata: Mapping[str, Any]
    global_seed: int | None
    targets: Dict[str, TargetMargins]

    def expand_points(self) -> List[MarginPoint]:
        base_values: Dict[str, Dict[str, Any]] = {}
        sweep_entries: List[tuple[str, str, Sequence[Any]]] = []

        for target_name, target in self.targets.items():
            target_values = dict(target.fixed)
            if target.jitter:
                target_values["jitter"] = target.jitter
            base_values[target_name] = target_values
            for parameter, values in target.sweeps.items():
                sweep_entries.append((target_name, parameter, tuple(values)))

        if not sweep_entries:
            point_id = "point-0"
            return [MarginPoint(point_id, base_values, self.global_seed or 0)]

        combos = itertools.product(*(entry[2] for entry in sweep_entries))
        points: List[MarginPoint] = []
        base_seed = self.global_seed or 0
        for idx, combo in enumerate(combos):
            values = {
                name: dict(inner) for name, inner in base_values.items()
            }
            for (target_name, parameter, _), chosen in zip(sweep_entries, combo):
                values.setdefault(target_name, {})[parameter] = chosen
            point_id = f"point-{idx}"
            points.append(MarginPoint(point_id, values, base_seed + idx))
        return points


@dataclass(slots=True)
class Bound:
    minimum: float | None = None
    maximum: float | None = None

    def validate(self, name: str, value: Any) -> None:
        if value is None:
            return
        numeric: float
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{name}: expected numeric value, got {value!r}") from exc
        if self.minimum is not None and numeric < self.minimum:
            raise SafetyViolationError(
                f"{name}: value {numeric} below minimum {self.minimum}"
            )
        if self.maximum is not None and numeric > self.maximum:
            raise SafetyViolationError(
                f"{name}: value {numeric} above maximum {self.maximum}"
            )


@dataclass(slots=True)
class SafetyPolicy:
    metadata: Mapping[str, Any]
    avt_bounds: Dict[str, Bound]
    behavior: Mapping[str, Any]

    def validate_value(self, name: str, value: Any) -> None:
        bound = self.avt_bounds.get(name)
        if not bound:
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                bound.validate(name, item)
            return
        bound.validate(name, value)
