"""Adapter manifest loading and execution."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping

from .exceptions import AdapterExecutionError, ValidationError
from .utils import load_yaml


@dataclass(slots=True)
class AdapterParameter:
    type: str
    allowed: Iterable[Any] | None = None
    minimum: float | None = None
    maximum: float | None = None

    def validate(self, name: str, value: Any) -> None:
        if self.allowed is not None and value not in self.allowed:
            raise ValidationError(f"adapter parameter '{name}': value {value!r} not in allowed set")
        if self.type in {"integer", "float"}:
            numeric: float
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                raise ValidationError(f"adapter parameter '{name}' expects numeric value") from exc
            if self.minimum is not None and numeric < self.minimum:
                raise ValidationError(
                    f"adapter parameter '{name}' value {numeric} below minimum {self.minimum}"
                )
            if self.maximum is not None and numeric > self.maximum:
                raise ValidationError(
                    f"adapter parameter '{name}' value {numeric} above maximum {self.maximum}"
                )


@dataclass(slots=True)
class AdapterManifest:
    name: str
    path: Path
    parameters: Dict[str, AdapterParameter] = field(default_factory=dict)
    description: str | None = None
    args: List[str] = field(default_factory=list)

    def build_command(self, parameters: Mapping[str, Any]) -> List[str]:
        for key, value in parameters.items():
            spec = self.parameters.get(key)
            if spec:
                spec.validate(key, value)
        command: List[str] = [str(self.path), *self.args]
        for key, value in parameters.items():
            flag = f"--{key.replace('_', '-')}"
            if isinstance(value, bool):
                if value:
                    command.append(flag)
                continue
            command.append(flag)
            command.append(str(value))
        return command


class AdapterRegistry:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._cache: MutableMapping[str, AdapterManifest] = {}

    def load(self) -> None:
        if not self._directory.exists():
            return
        for manifest_file in self._directory.glob("*.yaml"):
            payload = load_yaml(manifest_file)
            if not isinstance(payload, dict):
                raise ValidationError(f"{manifest_file}: adapter manifest must be mapping")
            name = payload.get("name")
            path = payload.get("path")
            if not name or not path:
                raise ValidationError(f"{manifest_file}: adapter 'name' and 'path' required")
            params_spec = payload.get("parameters", {})
            parameters: Dict[str, AdapterParameter] = {}
            if params_spec:
                if not isinstance(params_spec, dict):
                    raise ValidationError(f"{manifest_file}: parameters must be mapping")
                for param_name, spec in params_spec.items():
                    if not isinstance(spec, dict):
                        raise ValidationError(
                            f"{manifest_file}: parameter '{param_name}' spec must be mapping"
                        )
                    parameters[param_name] = AdapterParameter(
                        type=str(spec.get("type", "string")),
                        allowed=spec.get("allowed"),
                        minimum=spec.get("min"),
                        maximum=spec.get("max"),
                    )
            args = payload.get("args", [])
            if args and not isinstance(args, list):
                raise ValidationError(f"{manifest_file}: 'args' must be a list when provided")
            manifest = AdapterManifest(
                name=str(name),
                path=Path(path),
                parameters=parameters,
                description=payload.get("description"),
                args=[str(item) for item in args] if args else [],
            )
            self._cache[manifest.name] = manifest

    def get(self, name: str) -> AdapterManifest:
        if not self._cache:
            self.load()
        if name not in self._cache:
            raise ValidationError(f"unknown adapter '{name}'")
        return self._cache[name]


class AdapterExecutor:
    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    def run(
        self,
        name: str,
        parameters: Mapping[str, Any],
        stdout_path: Path,
        stderr_path: Path,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        manifest = self._registry.get(name)
        command = manifest.build_command(parameters)
        executable = shutil.which(command[0]) if manifest.path.is_absolute() else command[0]
        if manifest.path.is_absolute() and not manifest.path.exists():
            raise AdapterExecutionError(f"adapter '{name}' path '{manifest.path}' not found")
        if manifest.path.is_absolute():
            command[0] = str(manifest.path)
        elif executable:
            command[0] = executable
        else:
            raise AdapterExecutionError(f"adapter '{name}' executable '{command[0]}' not found")

        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr:
            result = subprocess.run(
                command,
                text=True,
                stdout=stdout,
                stderr=stderr,
                check=False,
                env=dict(env) if env else None,
            )
        if result.returncode != 0:
            raise AdapterExecutionError(
                f"adapter '{name}' failed with exit code {result.returncode}"
            )
        return result
