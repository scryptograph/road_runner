"""Run planning and execution."""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .adapters import AdapterExecutor, AdapterRegistry
from .artifacts import LDJSONLogger, RunPaths, sanitize, timestamp_now, write_summary
from .config import load_flow, load_margin_profile, load_safety_policy
from .exceptions import AdapterExecutionError
from .models import (
    FlowDefinition,
    FlowStep,
    MarginPoint,
    MarginProfile,
    SafetyPolicy,
    TargetMargins,
)
from .paths import adapters_dir, policy_file, runs_dir
from .sysinfo import collect_sysinfo
from .utils import dump_json, ensure_seed


@dataclass(slots=True)
class StepPlan:
    step: FlowStep
    invocations: List[Dict[str, Any]]
    margin: Dict[str, Any]


@dataclass(slots=True)
class SubRunPlan:
    identifier: str
    margin_point: MarginPoint
    steps: List[StepPlan]


@dataclass(slots=True)
class RunPlan:
    parent_id: str
    flow_path: Path
    margin_path: Path | None
    safety_source: str
    flow: FlowDefinition
    margin_profile: MarginProfile
    safety_policy: SafetyPolicy
    seed: int
    subruns: List[SubRunPlan] = field(default_factory=list)


def _default_margin_profile() -> MarginProfile:
    return MarginProfile(metadata={}, global_seed=None, targets={"default": TargetMargins()})


def _hash_identifier(parts: Iterable[str]) -> str:
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:10]
    return digest


def _generate_parent_run_id(flow_path: Path, seed: int) -> str:
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    hash_suffix = _hash_identifier((flow_path.as_posix(), str(seed), timestamp))
    return f"rr-{timestamp}-{hash_suffix}"


def _apply_margin_for_step(point: MarginPoint, adapter: str) -> Dict[str, Any]:
    combined: Dict[str, Any] = {}
    default_values = point.values.get("default", {})
    adapter_values = point.values.get(adapter, {})
    for source in (default_values, adapter_values):
        for key, value in source.items():
            if key == "jitter":
                continue
            combined[key] = value
    return combined


def _validate_safety(policy: SafetyPolicy, values: Mapping[str, Any]) -> None:
    for name, value in values.items():
        if name == "jitter":
            continue
        policy.validate_value(name, value)


class Runner:
    def __init__(
        self,
        adapters_path: Path | None = None,
        runs_path: Path | None = None,
        safety_policy_path: Path | None = None,
    ) -> None:
        self._adapters_path = adapters_path or adapters_dir()
        self._runs_path = runs_path or runs_dir()
        self._safety_policy_path = safety_policy_path or policy_file()
        self._registry = AdapterRegistry(self._adapters_path)
        self._executor = AdapterExecutor(self._registry)

    def plan(
        self,
        flow_path: Path,
        margin_path: Path | None = None,
        safety_policy: SafetyPolicy | None = None,
        safety_source: str | None = None,
    ) -> RunPlan:
        flow = load_flow(flow_path)
        margin_profile = load_margin_profile(margin_path) if margin_path else _default_margin_profile()
        safety = safety_policy or load_safety_policy(self._safety_policy_path)
        safety_identifier = (
            safety_source if safety_source is not None else self._safety_policy_path.as_posix()
        )

        seed = ensure_seed(margin_profile.global_seed)
        parent_id = _generate_parent_run_id(flow_path, seed)

        points = margin_profile.expand_points()
        subruns: List[SubRunPlan] = []
        for index, point in enumerate(points):
            for values in point.values.values():
                _validate_safety(safety, values)
            identifier = f"{parent_id}-s{index:02d}"
            step_plans: List[StepPlan] = []
            for step in flow.steps:
                step_margin = _apply_margin_for_step(point, step.adapter)
                _validate_safety(safety, step_margin)
                for parameter_key, parameter_value in step.parameters.items():
                    _validate_safety(safety, {parameter_key: parameter_value})
                for key, values in step.sweeps.items():
                    _validate_safety(safety, {key: list(values)})
                invocations = list(step.expanded_parameters())
                step_plans.append(StepPlan(step=step, invocations=invocations, margin=step_margin))
            subruns.append(SubRunPlan(identifier=identifier, margin_point=point, steps=step_plans))

        return RunPlan(
            parent_id=parent_id,
            flow_path=flow_path,
            margin_path=margin_path,
            safety_source=safety_identifier,
            flow=flow,
            margin_profile=margin_profile,
            safety_policy=safety,
            seed=seed,
            subruns=subruns,
        )

    def execute(
        self,
        plan: RunPlan,
        unit: str | None = None,
        dry_run: bool = False,
        sysinfo_override: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        run_base = self._runs_path
        run_paths = RunPaths(parent_id=plan.parent_id, base_dir=run_base)
        run_paths.parent_dir.mkdir(parents=True, exist_ok=True)

        plan_payload = self._serialize_plan(plan)
        dump_json(plan_payload, run_paths.plan_path)

        sysinfo = sysinfo_override or collect_sysinfo()
        dump_json(sysinfo, run_paths.sysinfo_path)
        dump_json(
            {
                "source": plan.safety_source,
                "metadata": dict(plan.safety_policy.metadata),
                "behavior": dict(plan.safety_policy.behavior),
                "avt_bounds": {
                    name: {"min": bound.minimum, "max": bound.maximum}
                    for name, bound in plan.safety_policy.avt_bounds.items()
                },
            },
            run_paths.safety_policy_path,
        )

        summary = {
            "run_id": plan.parent_id,
            "created_at": timestamp_now(),
            "unit": unit,
            "seed": plan.seed,
            "dry_run": dry_run,
            "flow": {"path": plan.flow_path.as_posix(), "metadata": plan.flow.metadata},
            "margin": {
                "path": plan.margin_path.as_posix() if plan.margin_path else None,
                "metadata": plan.margin_profile.metadata,
            },
            "safety_policy": {
                "source": plan.safety_source,
                "metadata": plan.safety_policy.metadata,
            },
            "environment": _environment_block(),
            "subruns": [],
        }

        write_summary(run_paths.summary_path, summary)

        if dry_run:
            return summary

        for subplan in plan.subruns:
            sub_summary = self._execute_subrun(plan, subplan, run_paths)
            summary["subruns"].append(sub_summary)
            write_summary(run_paths.summary_path, summary)

        from .reporting import render_reports

        render_reports(summary, summary["subruns"], run_paths)
        return summary

    def _execute_subrun(
        self,
        plan: RunPlan,
        subplan: SubRunPlan,
        run_paths: RunPaths,
    ) -> Dict[str, Any]:
        start = time.monotonic()
        sub_dir = run_paths.subrun_dir(subplan.identifier)
        sub_dir.mkdir(parents=True, exist_ok=True)
        ldjson_logger = LDJSONLogger(run_paths.subrun_ldjson(subplan.identifier))
        sub_summary: Dict[str, Any] = {
            "run_id": subplan.identifier,
            "margin": {
                "point_id": subplan.margin_point.identifier,
                "values": subplan.margin_point.values,
            },
            "status": "PENDING",
            "started_at": timestamp_now(),
            "steps": [],
        }
        status = "PASS"
        for step_index, step_plan in enumerate(subplan.steps):
            for invocation_index, parameters in enumerate(step_plan.invocations):
                step_label = (
                    step_plan.step.name
                    if len(step_plan.invocations) == 1
                    else f"{step_plan.step.name}[{invocation_index}]"
                )
                record_base = {
                    "event": "step",
                    "run_id": subplan.identifier,
                    "step": step_label,
                    "adapter": step_plan.step.adapter,
                    "parameters": parameters,
                }
                ldjson_logger.append({**record_base, "action": "start", "timestamp": timestamp_now()})
                step_start = time.monotonic()
                stdout_path = run_paths.step_stdout(
                    subplan.identifier, step_plan.step.name, step_index, invocation_index
                )
                stderr_path = run_paths.step_stderr(
                    subplan.identifier, step_plan.step.name, step_index, invocation_index
                )
                result_status = "PASS"
                error_message: str | None = None
                try:
                    env = _build_step_environment(
                        subplan,
                        plan,
                        step_plan,
                        parameters,
                    )
                    self._executor.run(
                        step_plan.step.adapter,
                        parameters,
                        stdout_path,
                        stderr_path,
                        env=env,
                    )
                except AdapterExecutionError as exc:
                    result_status = "FAIL"
                    error_message = str(exc)
                    status = "FAIL"
                step_duration = time.monotonic() - step_start
                ldjson_logger.append(
                    {
                        **record_base,
                        "action": "end",
                        "timestamp": timestamp_now(),
                        "status": result_status,
                        "duration_s": step_duration,
                        "error": error_message,
                    }
                )
                sub_summary["steps"].append(
                    {
                        "name": step_label,
                        "adapter": step_plan.step.adapter,
                        "status": result_status,
                        "duration_s": step_duration,
                        "parameters": parameters,
                        "artifacts": {
                            "stdout": stdout_path.relative_to(run_paths.parent_dir).as_posix(),
                            "stderr": stderr_path.relative_to(run_paths.parent_dir).as_posix(),
                        },
                        "margin": step_plan.margin,
                        "error": error_message,
                    }
                )
                if result_status != "PASS":
                    break
            if status != "PASS":
                break
        sub_summary["status"] = status
        sub_summary["duration_s"] = time.monotonic() - start
        sub_summary["completed_at"] = timestamp_now()
        sub_summary_path = run_paths.subrun_summary(subplan.identifier)
        write_summary(sub_summary_path, sub_summary)
        return sub_summary

    def _serialize_plan(self, plan: RunPlan) -> Dict[str, Any]:
        return {
            "run_id": plan.parent_id,
            "flow": {
                "path": plan.flow_path.as_posix(),
                "metadata": plan.flow.metadata,
            },
            "margin": {
                "path": plan.margin_path.as_posix() if plan.margin_path else None,
                "metadata": plan.margin_profile.metadata,
            },
            "safety_policy": {
                "source": plan.safety_source,
                "metadata": plan.safety_policy.metadata,
                "behavior": plan.safety_policy.behavior,
                "avt_bounds": {
                    name: {"min": bound.minimum, "max": bound.maximum}
                    for name, bound in plan.safety_policy.avt_bounds.items()
                },
            },
            "seed": plan.seed,
            "subruns": [
                {
                    "run_id": sub.identifier,
                    "margin_point": {
                        "id": sub.margin_point.identifier,
                        "values": sub.margin_point.values,
                        "seed": sub.margin_point.seed,
                    },
                    "steps": [
                        {
                            "name": step.step.name,
                            "adapter": step.step.adapter,
                            "margin": step.margin,
                            "invocations": step.invocations,
                        }
                        for step in sub.steps
                    ],
                }
                for sub in plan.subruns
            ],
        }


def _environment_block() -> Dict[str, Any]:
    import importlib
    import platform
    import sys

    versions = {
        "python": sys.version,
        "platform": platform.platform(),
    }
    for module_name in ("typer", "jinja2", "PyYAML"):
        try:
            module = importlib.import_module(module_name)
            versions[module_name] = getattr(module, "__version__", "unknown")
        except ModuleNotFoundError:
            continue
    from . import __version__

    versions["road_runner"] = __version__
    return versions


def _build_step_environment(
    subplan: SubRunPlan,
    plan: RunPlan,
    step_plan: StepPlan,
    parameters: Mapping[str, Any],
) -> Dict[str, str]:
    env = dict(os.environ)
    env["RR_RUN_ID"] = plan.parent_id
    env["RR_SUB_RUN_ID"] = subplan.identifier
    env["RR_STEP_ADAPTER"] = step_plan.step.adapter
    env["RR_STEP_NAME"] = step_plan.step.name
    for key, value in parameters.items():
        env_key = f"RR_PARAM_{sanitize(key).upper()}"
        env[env_key] = str(value)
    margin_values = step_plan.margin
    for key, value in margin_values.items():
        env_key = f"RR_MARGIN_{sanitize(key).upper()}"
        env[env_key] = str(value)
    env["RR_MARGIN_POINT"] = subplan.margin_point.identifier
    env["RR_GLOBAL_SEED"] = str(plan.seed)
    return env
