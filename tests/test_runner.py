import sys
from pathlib import Path

from road_runner.runner import Runner


def _prepare_environment(base: Path) -> tuple[Path, Path, Path, Path]:
    adapters_dir = base / "adapters"
    adapters_dir.mkdir()
    diags_dir = base / "diags"
    diags_dir.mkdir()
    script = diags_dir / "adapter_stub.py"
    script.write_text(
        """#!/usr/bin/env python3
import argparse
import time

parser = argparse.ArgumentParser()
parser.add_argument("--duration", type=float, default=0.0)
parser.add_argument("--message", type=str, default="")
args = parser.parse_args()

time.sleep(min(args.duration, 0.01))
print(args.message)
""",
        encoding="utf-8",
    )
    manifest = adapters_dir / "echo.yaml"
    manifest.write_text(
        f"""
name: echo
path: {sys.executable}
args:
  - {str(script)}
parameters:
  duration:
    type: float
    min: 0
    max: 10
  message:
    type: string
""",
        encoding="utf-8",
    )

    flows_dir = base / "flows"
    flows_dir.mkdir()
    flow_path = flows_dir / "sample.yaml"
    flow_path.write_text(
        """
metadata: {}
steps:
  - name: echo-step
    adapter: echo
    parameters:
      duration: 0.001
      message: hello
""",
        encoding="utf-8",
    )

    margins_dir = base / "margins"
    margins_dir.mkdir()
    margin_path = margins_dir / "default.yaml"
    margin_path.write_text(
        """
metadata: {}
targets:
  default:
    vcore_mv: 950
""",
        encoding="utf-8",
    )

    policy_dir = base / "policy"
    policy_dir.mkdir()
    policy_path = policy_dir / "safety.yaml"
    policy_path.write_text(
        """
metadata: {}
avt_bounds:
  vcore_mv:
    min: 900
    max: 1000
behavior: {}
""",
        encoding="utf-8",
    )

    runs_dir = base / "runs"
    runs_dir.mkdir()
    return flow_path, margin_path, policy_path, adapters_dir


def test_runner_execute_creates_artifacts(tmp_path: Path) -> None:
    flow_path, margin_path, policy_path, adapters_dir = _prepare_environment(tmp_path)
    runner = Runner(
        adapters_path=adapters_dir,
        runs_path=tmp_path / "runs",
        safety_policy_path=policy_path,
    )
    plan = runner.plan(flow_path=flow_path, margin_path=margin_path)
    summary = runner.execute(plan, unit="unit-42")
    assert summary["subruns"]
    subrun = summary["subruns"][0]
    assert subrun["steps"][0]["status"] == "PASS"
    run_dir = tmp_path / "runs" / summary["run_id"]
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "report.md").exists()
    assert (run_dir / "safety_policy.json").exists()
