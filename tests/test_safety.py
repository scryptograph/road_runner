from pathlib import Path

from road_runner.safety import SafetyProfileEngine, load_policy_from_profile


def test_safety_profile_engine_matches(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    profile_path = profiles_dir / "genoa.yaml"
    profile_path.write_text(
        """
profile:
  name: genoa
match:
  cpu_model_contains: ["EPYC"]
  min_cores: 8
policy:
  metadata:
    name: genoa
  avt_bounds:
    vcore_mv:
      min: 900
      max: 1050
  behavior:
    on_violation: abort
""",
        encoding="utf-8",
    )

    engine = SafetyProfileEngine(profiles_dir)
    sysinfo = {
        "lscpu": "Model name: AMD EPYC 9274F\nCPU(s): 16\nArchitecture: x86_64",
        "uname": "Linux test-host 6.8.0-rc",
    }
    profile = engine.select(sysinfo)
    assert profile is not None
    assert profile.policy.avt_bounds["vcore_mv"].maximum == 1050


def test_load_policy_from_profile_handles_plain_policy(tmp_path: Path) -> None:
    policy_path = tmp_path / "safety.yaml"
    policy_path.write_text(
        """
metadata:
  name: default
avt_bounds:
  vcore_mv:
    min: 900
    max: 1000
behavior:
  on_violation: abort
""",
        encoding="utf-8",
    )
    policy = load_policy_from_profile(policy_path)
    assert policy.avt_bounds["vcore_mv"].maximum == 1000
