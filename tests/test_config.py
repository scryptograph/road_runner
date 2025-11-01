from pathlib import Path

import pytest

from road_runner.config import load_flow, load_margin_profile, load_safety_policy
from road_runner.exceptions import SafetyViolationError
from road_runner.models import FlowDefinition, MarginProfile, SafetyPolicy


def test_flow_loading(tmp_path: Path) -> None:
    flow_path = tmp_path / "flow.yaml"
    flow_path.write_text(
        """
metadata:
  name: demo
steps:
  - name: step-one
    adapter: adapter-one
    parameters:
      foo: 1
    sweeps:
      bar: [1, 2]
""",
        encoding="utf-8",
    )
    definition = load_flow(flow_path)
    assert isinstance(definition, FlowDefinition)
    assert definition.steps[0].name == "step-one"
    expanded = list(definition.steps[0].expanded_parameters())
    assert len(expanded) == 2


def test_margin_profile_expansion(tmp_path: Path) -> None:
    margin_path = tmp_path / "margin.yaml"
    margin_path.write_text(
        """
metadata: {}
global_seed: 100
targets:
  default:
    vcore_mv:
      sweep: [900, 950]
    soc_freq_mhz: 1800
""",
        encoding="utf-8",
    )
    profile = load_margin_profile(margin_path)
    assert isinstance(profile, MarginProfile)
    points = profile.expand_points()
    assert len(points) == 2
    assert points[0].values["default"]["soc_freq_mhz"] == 1800


def test_safety_policy_loading(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        """
metadata: {}
avt_bounds:
  vcore_mv:
    min: 900
    max: 1000
behavior:
  on_violation: abort
""",
        encoding="utf-8",
    )
    policy = load_safety_policy(policy_path)
    assert isinstance(policy, SafetyPolicy)
    policy.validate_value("vcore_mv", 950)
    with pytest.raises(SafetyViolationError):
        policy.validate_value("vcore_mv", 1100)
