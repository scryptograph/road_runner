# Quick Start

1. Install dependencies:
   ```shell
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```
2. Prepare YAML inputs:
   - Place flow definitions under `flows/`.
   - Place margin profiles under `margins/`.
   - Update the safety policy in `policy/safety.yaml`.
   - (Optional) Add hardware-specific safety profiles under `policy/profiles/`.
   - Place diagnostic binaries (stubs or real) under `diags/` and reference them from adapter manifests.
3. Plan a run:
   ```shell
   road_runner plan --flow flows/sample_flow.yaml --margin margins/sample_margin.yaml
   ```
4. Execute:
   ```shell
   road_runner run --flow flows/sample_flow.yaml --margin margins/sample_margin.yaml
   ```
5. Generate reports:
   ```shell
   road_runner report --run-id <RUN_ID>
   road_runner export --run <PARENT_RUN_ID> --format csv
   ```
