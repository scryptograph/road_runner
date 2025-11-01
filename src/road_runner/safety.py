"""Safety profile engine for automatic policy selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import parse_safety_policy
from .exceptions import ValidationError
from .models import SafetyPolicy
from .paths import policy_profiles_dir
from .utils import load_yaml


@dataclass(slots=True)
class HardwareFingerprint:
    cpu_model: str
    total_cores: Optional[int]
    architecture: str

    @classmethod
    def from_sysinfo(cls, sysinfo: Dict[str, str]) -> "HardwareFingerprint":
        lscpu_output = sysinfo.get("lscpu", "")
        uname_output = sysinfo.get("uname", "")
        parsed = _parse_lscpu(lscpu_output)
        cpu_model = parsed.get("model name", "").strip()
        architecture = parsed.get("architecture", "").strip() or uname_output
        total_cores = None
        cpu_count = parsed.get("cpu(s)")
        if cpu_count:
            try:
                total_cores = int(cpu_count.split()[0])
            except ValueError:
                total_cores = None
        return cls(cpu_model=cpu_model, total_cores=total_cores, architecture=architecture)


@dataclass(slots=True)
class SafetyProfile:
    name: str
    description: Optional[str]
    priority: int
    match: Dict[str, Any]
    policy: SafetyPolicy
    source_path: Path


class SafetyProfileEngine:
    def __init__(self, profiles_path: Path | None = None) -> None:
        self._profiles_path = profiles_path or policy_profiles_dir()
        self._profiles: List[SafetyProfile] = []
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        if not self._profiles_path.exists():
            self._loaded = True
            return
        for path in sorted(self._profiles_path.glob("*.y*ml")):
            payload = load_yaml(path)
            if not isinstance(payload, dict):
                raise ValidationError(f"{path}: safety profile must be a mapping")
            profile_meta = payload.get("profile", {}) or {}
            if profile_meta and not isinstance(profile_meta, dict):
                raise ValidationError(f"{path}: 'profile' must be mapping when present")
            match_criteria = payload.get("match", {}) or {}
            if match_criteria and not isinstance(match_criteria, dict):
                raise ValidationError(f"{path}: 'match' must be mapping when present")
            policy_payload = payload.get("policy")
            if not isinstance(policy_payload, dict):
                raise ValidationError(f"{path}: 'policy' section is required")
            policy = parse_safety_policy(policy_payload, f"{path} policy")
            profile = SafetyProfile(
                name=str(profile_meta.get("name", path.stem)),
                description=profile_meta.get("description"),
                priority=int(profile_meta.get("priority", 0)),
                match=match_criteria,
                policy=policy,
                source_path=path,
            )
            self._profiles.append(profile)
        self._profiles.sort(key=lambda profile: profile.priority, reverse=True)
        self._loaded = True

    def select(self, sysinfo: Dict[str, str]) -> Optional[SafetyProfile]:
        self.load()
        if not self._profiles:
            return None
        fingerprint = HardwareFingerprint.from_sysinfo(sysinfo)
        for profile in self._profiles:
            if _matches(profile.match, fingerprint):
                return profile
        return None

    def fingerprint(self, sysinfo: Dict[str, str]) -> HardwareFingerprint:
        return HardwareFingerprint.from_sysinfo(sysinfo)


def _parse_lscpu(output: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip().lower()] = value.strip()
    return parsed


def _matches(criteria: Dict[str, Any], fingerprint: HardwareFingerprint) -> bool:
    cpu_model = fingerprint.cpu_model.lower()
    architecture = fingerprint.architecture.lower()
    total_cores = fingerprint.total_cores

    model_contains = _ensure_list(criteria.get("cpu_model_contains"))
    if model_contains and not any(substr.lower() in cpu_model for substr in model_contains):
        return False

    arch_contains = _ensure_list(criteria.get("architecture_contains"))
    if arch_contains and not any(substr.lower() in architecture for substr in arch_contains):
        return False

    min_cores = criteria.get("min_cores")
    if min_cores is not None and total_cores is not None and total_cores < int(min_cores):
        return False

    max_cores = criteria.get("max_cores")
    if max_cores is not None and total_cores is not None and total_cores > int(max_cores):
        return False

    return True


def _ensure_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def load_policy_from_profile(path: Path) -> SafetyPolicy:
    payload = load_yaml(path)
    if not isinstance(payload, dict):
        raise ValidationError(f"{path}: safety profile must be a mapping")
    if "policy" in payload:
        policy_payload = payload["policy"]
        if not isinstance(policy_payload, dict):
            raise ValidationError(f"{path}: 'policy' section must be mapping")
        return parse_safety_policy(policy_payload, f"{path} policy")
    return parse_safety_policy(payload, f"{path}")
