# Road Runner - System-Level Test Execution Engine

`road_runner` is a deterministic, file-driven orchestration tool for running system diagnostics on a Linux host. You define *what* to run using YAML files (flows, margin profiles, and safety policies) and the CLI takes care of planning, executing, and collecting artifacts for each diagnostic step.

The tool is designed for engineers who need to reproduce elusive failures on real hardware by sweeping voltage and frequency settings, recording every run in a reproducible way, and generating reports that are easy to share.

---

## Why Road Runner Exists (Layman Overview)

1. **Describe your experiment** - Write a flow YAML with the diagnostics (adapters) to launch and the parameters they need.  
2. **Define safe limits** - Safety policy YAML ensures you never push voltage/frequency values outside approved bounds.  
3. **Optionally sweep margins** - Margin profile YAML can sweep AVT rails (voltage/frequency pairs) or set fixed recipes.  
4. **Run the CLI** - `road_runner run --flow ... --margin ...` executes the plan locally, step by step.  
5. **Collect artifacts** - Each run produces structured JSON summaries, LDJSON step logs, stdout/stderr captures, sysinfo snapshots, and HTML/Markdown/CSV reports.  
6. **Stay deterministic** - A global seed and recorded dependency versions allow you to replay the exact same run later.

---

## Repository Layout

```
road_runner/
|- adapters/              # Adapter manifests (one YAML per diagnostic binary)
|- diags/                 # Stub diagnostics (e.g., mprime, mem tests)
|- docs/                  # Additional documentation
|- flows/                 # Flow definitions (YAML)
|- margins/               # Margin profiles (YAML)
|- policy/                # Safety policy (YAML) and auto-profiles
|  |- profiles/           # Hardware-aware safety profiles (auto-selected)
|- src/road_runner/       # Python source code
|  |- cli.py              # Typer CLI entry point
|  |- runner.py           # Planning + execution engine
|  |- config.py           # YAML loaders and validation
|  |- adapters.py         # Adapter manifests and subprocess runner
|  |- artifacts.py        # Paths, LDJSON logger, summary helpers
|  |- models.py           # Dataclasses for flows, margins, safety bounds
|  |- reporting.py        # Markdown/HTML report rendering
|  |- exporter.py         # CSV export logic
|  |- sysinfo.py          # Host information snapshot
|  |- utils.py            # Common helpers
|  |- exceptions.py       # Custom error types
|- templates/             # Jinja2 templates for reports
|- tests/                 # Pytest suites (config parsing and runner smoke)
|- README.md              # You are here
|- pyproject.toml         # Packaging, dependencies, lint/test config
|- .gitignore
```

---

## Architectural Highlights

- **CLI-first**: The entire workflow is accessed through the `road_runner` Typer CLI (packaged entry point).  
- **File-based inputs**: Flows, margin profiles, and safety policies are YAML files stored under dedicated folders for discoverability (`./flows`, `./margins`, `./policy`).  
- **Deterministic planning**: Margin sweeps are expanded upfront into parent/child runs. Each child run receives deterministic seeds and margin values derived from the profile (see `MarginProfile.expand_points`).  
- **Safety guardrails**: Safety policy bounds are enforced during planning and before step execution; auto-selected profiles can derive these bounds from detected hardware at runtime.  
- **Adapters as manifests**: Each diagnostic binary is described by a YAML manifest specifying its executable inside `./diags/`, optional argument prelude, and parameter metadata (`AdapterManifest`). The runner validates CLI flag inputs before launching the process.  
- **Artifacts per run**: A unique run directory under `./runs/<RUN_ID>` stores the plan, summaries, sysinfo, LDJSON step logs, stdout/stderr captures, and Markdown/HTML reports.  
- **Reporting pipeline**: After execution, Jinja2 templates render Markdown + HTML reports, and a CSV exporter consolidates per-step metrics across sweep runs.  
- **Extensibility**: Add new adapters by dropping manifests in `adapters/`; add new flow/margin definitions without touching code; override report templates by editing files under `templates/`.

---

## Key Concepts (Simplified)

| Concept            | Explanation |
|--------------------|-------------|
| **Flow**           | Ordered list of diagnostic steps. Each step references an adapter (binary) and parameters. Steps can include sweeps to run the same adapter with multiple parameter combinations. |
| **Margin Profile** | Defines voltage/frequency (AVT) settings. Supports fixed values or sweep lists per target (global/default or adapter-specific). |
| **Safety Policy**  | Hard upper/lower bounds for AVT and other parameters. Every planned value must fit inside these bounds before the run proceeds. |
| **Adapter**        | The actual executable launched for each step. A manifest declares its path and supported parameters so Road Runner can build the command line safely. |
| **Run**            | Execution of a flow + margin combination. A parent run can contain multiple sub-runs if the margin profile expands to several points. |
| **Artifacts**      | Structured data and logs saved per run: JSON summaries, LDJSON step logs, stdout/stderr, system snapshot, Markdown/HTML/CSV reports. |

---

## Installing & Developing

```bash
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows
pip install -e ".[dev]"

# Linting & type checks
ruff check src
mypy src

# Run tests
python -m pytest
```

Road Runner targets Python 3.11+. The `pyproject.toml` exposes `road_runner` as a script entry point, so once installed you can run the CLI directly.

---

## CLI Usage Walkthrough

### 1. Inspect available assets

```bash
road_runner list-flows
road_runner margins list
road_runner margins validate --file margins/sample_margin.yaml
```

### 2. Plan a run (no execution)

```bash
road_runner plan \
  --flow flows/sample_flow.yaml \
  --margin margins/sample_margin.yaml
```

This prints the expansion matrix: every sub-run and adapter invocation that would execute.

### 3. Execute the plan

```bash
road_runner run \
  --flow flows/sample_flow.yaml \
  --margin margins/sample_margin.yaml \
  --unit SN123456
```

During execution the CLI inspects the host (via `lscpu`, `uname`, etc.), selects the highest-priority matching safety profile from `policy/profiles/`, and shows the proposed voltage/frequency bounds. Confirm to continue or decline to abort so you can adjust the limits.

Artifacts will be written under `runs/<RUN_ID>/` with reports accessible at:

```
runs/<RUN_ID>/report.md
runs/<RUN_ID>/report.html
```

Use `--dry-run` to generate the plan, sysinfo, and summaries without launching adapters.

### 4. Reports and exports

```bash
road_runner report --run-id <RUN_ID>      # Re-render Markdown/HTML from saved JSON
road_runner export --run <RUN_ID> --format csv
```

### 5. Maintenance commands

```bash
road_runner clean --older-than 7         # Remove runs older than N days
road_runner rerun-last                   # Repeat the most recent successful run
```

---

## What Each Command Produces

| Command                           | Outcome |
|-----------------------------------|---------|
| `road_runner plan`                | JSON plan persisted to `runs/<RUN_ID>/plan.json`; nothing executed. |
| `road_runner run`                 | Creates parent + sub-run directories, LDJSON logs, stdout/stderr, summary, sysinfo, Markdown/HTML reports. Stub diagnostics in `./diags/` are executed for the sample flow. |
| `road_runner report`              | Rebuilds reports from existing JSON (useful after editing templates). |
| `road_runner export --format csv` | Generates a CSV rolling up step metrics across sub-runs. |
| `road_runner clean`               | Deletes run directories older than a specified number of days. |
| `road_runner rerun-last`          | Resolves the latest run from `runs/` and re-executes it with the same flow/margin combo. |

---

## Run Directory Anatomy

For a parent run `rr-20250101T010101Z-abc123` youll see:

```
runs/rr-20250101T010101Z-abc123/
""" report.html
""" report.md
""" plan.json
""" summary.json
""" sysinfo.json
"""" subruns/
    """ rr-2025...-s00/
    "   """ steps.ldjson
    "   """ summary.json
    "   """ stdout/
    "   "   """" 00_cpu-smoke.log
    "   """" stderr/
    "       """" 00_cpu-smoke.log
    """" rr-2025...-s01/
        """" ...
```

Each `steps.ldjson` contains newline-delimited JSON entries capturing start/end timestamps, status, duration, and any adapter errors. The `summary.json` rolls all step outcomes together for quick consumption by other tools.

---

## Safety & Determinism

- **Automatic Profile Selection**: On each `road_runner run`, the safety engine parses `lscpu`/`uname`, matches against `policy/profiles/*.yaml`, and proposes the best-fit policy for your hardware. You can keep the default `policy/safety.yaml` or tighten bounds per product line.  
- **Global Seed**: The margin profile can specify `global_seed`. When present, it seeds Python's RNG and is baked into run IDs so repeated runs remain reproducible. When absent, the runner picks a seed and records it in the summary.  
- **Policy Enforcement**: Before an adapter runs, the aggregated margins and sweep values are checked against the safety policy bounds. Violations raise `SafetyViolationError` and the run stops.  
- **Environment Snapshot**: `sysinfo.collect_sysinfo()` captures CPU, memory, kernel, sensors (if available), and utility versions so you can compare environment drift between runs.

---

## Common Use Cases

1. **Hardware Margins Regression** - Sweep core voltage and frequency combinations before a new firmware release, keeping a deterministic record of failing combinations.  
2. **Reproduce Field Issue** - Load the exact flow and margin profile that triggered a customer failure, rerun locally or on a lab system, and attach the generated report to the investigation.  
3. **Adapter Certification** - Validate that a new diagnostic binary respects safety policies and integrates cleanly with existing flows before handing it to the broader team.

---

## Extending Road Runner

- **Add a new adapter**: Create `adapters/<name>.yaml` with the binary path (ideally under `./diags/`), optional `args`, and parameter schema.  
- **Create new flows**: Drop YAML files into `flows/` referencing adapters and parameters.  
- **Define new margin sweeps**: Add YAML profiles in `margins/`, mixing fixed values and sweeps; add jitter schema details if needed.  
- **Extend safety coverage**: Add `policy/profiles/<family>.yaml` with `match` rules (`cpu_model_contains`, `min_cores`, etc.) plus a `policy` block to auto-select limits per product line.  
- **Custom reports**: Edit or replace templates in `templates/report.md.j2` or `report.html.j2`. Re-run `road_runner report --run-id ...` to regenerate artifacts.  
- **Automation integration**: Consume `runs/<RUN_ID>/summary.json` and `steps.ldjson` from CI/cron jobs to trigger alerts or analytics.

---

## Troubleshooting Cheatsheet

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `validation failed` errors | Flow/margin values out of bounds | Adjust values or update `policy/safety.yaml` |
| `adapter ... executable not found` | Manifest path incorrect or binary missing on host | Verify `path`/`args` in adapter manifest and ensure binary is installed |
| `ModuleNotFoundError: pytest` during tests | Dev dependencies not installed | Run `pip install -e ".[dev]"` |
| Reports missing | Run may have failed early | Check `runs/<RUN_ID>/summary.json` and LDJSON for step errors |

---

## Additional Resources

- `docs/quickstart.md` " short version of setup + execution steps.
- `tests/` " examples of how flows/margins/policies interact; useful when writing new fixtures.
- Sample YAML files in `flows/`, `margins/`, `policy/`, `adapters/` " starting point for your own definitions.

---

## License

MIT



