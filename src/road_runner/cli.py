"""Typer CLI for road_runner."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .artifacts import RunPaths
from .config import load_margin_profile, load_safety_policy
from .exporter import export_csv
from .exceptions import RoadRunnerError, ValidationError
from .models import SafetyPolicy
from .paths import flows_dir, margins_dir, policy_file, policy_profiles_dir, runs_dir
from .reporting import render_reports
from .runner import Runner
from .safety import SafetyProfileEngine, load_policy_from_profile
from .sysinfo import collect_sysinfo
from .utils import read_json

app = typer.Typer(help="Road Runner system-level test execution engine.")

console = Console()


def _format_policy_table(policy: SafetyPolicy) -> Table:
    table = Table(title="Safety Policy Bounds")
    table.add_column("Parameter")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")
    for name, bound in sorted(policy.avt_bounds.items()):
        table.add_row(
            name,
            "-" if bound.minimum is None else str(bound.minimum),
            "-" if bound.maximum is None else str(bound.maximum),
        )
    return table


@app.command()
def run(
    flow: Path = typer.Option(..., "--flow", exists=True, dir_okay=False, resolve_path=True),
    unit: Optional[str] = typer.Option(None, "--unit", help="Unit under test identifier"),
    margin: Optional[Path] = typer.Option(
        None, "--margin", exists=True, dir_okay=False, resolve_path=True
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Do not execute adapters"),
) -> None:
    """Execute a flow with optional margin profile."""
    sysinfo_snapshot = collect_sysinfo()
    safety_engine = SafetyProfileEngine(policy_profiles_dir())
    fingerprint = safety_engine.fingerprint(sysinfo_snapshot)
    cpu_label = fingerprint.cpu_model or fingerprint.architecture or "unknown CPU"
    selected_profile = safety_engine.select(sysinfo_snapshot)
    safety_policy = None
    safety_source = None
    if selected_profile:
        console.print(f"[cyan]Detected CPU:[/] {cpu_label}")
        console.print(
            f"[cyan]Auto-selected safety profile:[/] {selected_profile.name} "
            f"(source: {selected_profile.source_path.name})"
        )
        if selected_profile.description:
            console.print(selected_profile.description)
        console.print(_format_policy_table(selected_profile.policy))
        confirm = typer.confirm(
            f"Use safety profile '{selected_profile.name}' from {selected_profile.source_path.name}?",
            default=True,
        )
        if not confirm:
            raise typer.Exit("Run cancelled by user.")
        safety_policy = selected_profile.policy
        safety_source = selected_profile.source_path.as_posix()
    else:
        console.print(
            f"[yellow]No safety profile matched current system ({cpu_label}). "
            "Falling back to policy/safety.yaml[/yellow]"
        )

    runner = Runner()
    try:
        plan = runner.plan(
            flow_path=flow,
            margin_path=margin,
            safety_policy=safety_policy,
            safety_source=safety_source,
        )
        summary = runner.execute(
            plan,
            unit=unit,
            dry_run=dry_run,
            sysinfo_override=sysinfo_snapshot,
        )
    except RoadRunnerError as exc:
        raise typer.Exit(f"error: {exc}") from exc
    console.print(f"[green]Run {summary['run_id']} prepared[/green]")
    if dry_run:
        console.print("Dry run: no adapters executed.")
    else:
        console.print("Reports available at:")
        console.print(f"  Markdown: {runs_dir() / summary['run_id'] / 'report.md'}")
        console.print(f"  HTML: {runs_dir() / summary['run_id'] / 'report.html'}")


@app.command("list-flows")
def list_flows() -> None:
    """List available flows."""
    directory = flows_dir()
    files = sorted(directory.glob("*.y*ml"))
    if not files:
        console.print("No flows found under ./flows")
        raise typer.Exit()
    table = Table(title="Available Flows")
    table.add_column("Flow File")
    for file in files:
        table.add_row(file.name)
    console.print(table)


margins_app = typer.Typer(help="Margin profile utilities.")


@margins_app.command("list")
def list_margins() -> None:
    directory = margins_dir()
    files = sorted(directory.glob("*.y*ml"))
    if not files:
        console.print("No margin profiles found under ./margins")
        raise typer.Exit()
    table = Table(title="Available Margin Profiles")
    table.add_column("Profile File")
    for file in files:
        table.add_row(file.name)
    console.print(table)


def _validate_margin_against_policy(policy: SafetyPolicy, profile_path: Path) -> None:
    profile = load_margin_profile(profile_path)
    points = profile.expand_points()
    for point in points:
        for target, values in point.values.items():
            for key, value in values.items():
                if key == "jitter":
                    continue
                policy.validate_value(key, value)


@margins_app.command("validate")
def validate_margin(
    file: Path = typer.Option(..., "--file", exists=True, dir_okay=False, resolve_path=True)
) -> None:
    policy = load_safety_policy(policy_file())
    try:
        _validate_margin_against_policy(policy, file)
    except ValidationError as exc:
        raise typer.Exit(f"validation failed: {exc}") from exc
    console.print(f"[green]{file.name} is valid against current safety policy[/green]")


app.add_typer(margins_app, name="margins")


@app.command()
def plan(
    flow: Path = typer.Option(..., "--flow", exists=True, dir_okay=False, resolve_path=True),
    margin: Optional[Path] = typer.Option(
        None, "--margin", exists=True, dir_okay=False, resolve_path=True
    ),
) -> None:
    """Preview run plan without executing."""
    runner = Runner()
    plan_obj = runner.plan(flow_path=flow, margin_path=margin)
    table = Table(title=f"Plan for {plan_obj.parent_id}")
    table.add_column("Sub-Run")
    table.add_column("Margin Point")
    table.add_column("Details")
    for subrun in plan_obj.subruns:
        margin_details = json.dumps(subrun.margin_point.values, indent=2)
        details_lines = []
        for step in subrun.steps:
            details_lines.append(f"{step.step.name} ({step.step.adapter}) x{len(step.invocations)}")
        table.add_row(subrun.identifier, subrun.margin_point.identifier, "\n".join(details_lines))
    console.print(table)


@app.command()
def report(
    run_id: str = typer.Option(..., "--run-id", help="Run identifier to regenerate report for")
) -> None:
    run_path = runs_dir() / run_id
    summary_path = run_path / "summary.json"
    if not summary_path.exists():
        raise typer.Exit(f"summary not found for run {run_id}")
    summary = read_json(summary_path)
    subruns = summary.get("subruns", [])
    run_paths = RunPaths(parent_id=run_id, base_dir=runs_dir())
    render_reports(summary, subruns, run_paths)
    console.print(f"[green]Regenerated reports for {run_id}[/green]")


@app.command()
def export(
    run: str = typer.Option(..., "--run", help="Parent run identifier"),
    format: str = typer.Option(..., "--format", help="Export format", case_sensitive=False),
) -> None:
    if format.lower() != "csv":
        raise typer.Exit("only csv export is supported")
    run_path = runs_dir() / run
    if not run_path.exists():
        raise typer.Exit(f"run directory {run_path} not found")
    destination = export_csv(run_path)
    console.print(f"[green]Exported CSV to {destination}[/green]")


@app.command()
def clean(
    older_than: int = typer.Option(
        ..., "--older-than", help="Remove runs older than N days", min=1
    )
) -> None:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=older_than)
    removed = 0
    for run_dir in runs_dir().glob("rr-*"):
        summary = run_dir / "summary.json"
        if not summary.exists():
            continue
        mtime = datetime.fromtimestamp(summary.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            shutil.rmtree(run_dir, ignore_errors=True)
            removed += 1
    console.print(f"Removed {removed} runs older than {older_than} days.")


@app.command("rerun-last")
def rerun_last() -> None:
    candidates = list(runs_dir().glob("rr-*/summary.json"))
    if not candidates:
        raise typer.Exit("no previous runs found")
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    summary = read_json(candidates[0])
    flow_path = Path(summary["flow"]["path"])
    margin_path = summary["margin"]["path"]
    if not flow_path.exists():
        raise typer.Exit(f"flow path {flow_path} not found")
    margin = Path(margin_path) if margin_path and Path(margin_path).exists() else None
    safety_info = summary.get("safety_policy", {})
    safety_source = safety_info.get("source")
    safety_policy = None
    if safety_source:
        source_path = Path(safety_source)
        if source_path.exists():
            try:
                safety_policy = load_policy_from_profile(source_path)
            except ValidationError as exc:
                console.print(
                    f"[yellow]Failed to load safety policy from {safety_source}: {exc}. "
                    "Falling back to default policy.[/yellow]"
                )
                safety_policy = None
        else:
            console.print(
                f"[yellow]Recorded safety policy {safety_source} missing. Using default policy.[/yellow]"
            )
    runner = Runner()
    plan_obj = runner.plan(
        flow_path=flow_path,
        margin_path=margin,
        safety_policy=safety_policy,
        safety_source=safety_source if safety_policy else None,
    )
    summary = runner.execute(plan_obj, unit=summary.get("unit"))
    console.print(f"[green]Re-ran latest run as {summary['run_id']}[/green]")


if __name__ == "__main__":
    app()
