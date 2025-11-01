"""Reporting utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .artifacts import RunPaths
from .paths import templates_dir


def _jinja_environment() -> Environment:
    template_path = templates_dir()
    loader = FileSystemLoader(str(template_path)) if template_path.exists() else None
    env = Environment(
        loader=loader,
        autoescape=select_autoescape(enabled_extensions=("html",)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["len"] = len
    return env


def _render_template(env: Environment, template_name: str, fallback: str, context: Dict[str, Any]) -> str:
    if env.loader and env.loader.get_source:  # type: ignore[attr-defined]
        try:
            template = env.get_template(template_name)
            return template.render(**context)
        except Exception:
            pass
    template = env.from_string(fallback)
    return template.render(**context)


def render_reports(summary: Dict[str, Any], subruns: List[Dict[str, Any]], run_paths: RunPaths) -> None:
    env = _jinja_environment()
    context = {
        "summary": summary,
        "subruns": subruns,
    }
    markdown = _render_template(
        env,
        "report.md.j2",
        fallback=_DEFAULT_MARKDOWN_TEMPLATE,
        context=context,
    )
    html = _render_template(
        env,
        "report.html.j2",
        fallback=_DEFAULT_HTML_TEMPLATE,
        context=context,
    )
    run_paths.parent_dir.mkdir(parents=True, exist_ok=True)
    run_paths.markdown_report_path.write_text(markdown, encoding="utf-8")
    run_paths.html_report_path.write_text(html, encoding="utf-8")


_DEFAULT_MARKDOWN_TEMPLATE = """# Road Runner Report

## Run Summary

- Run ID: {{ summary.run_id }}
- Flow: {{ summary.flow.path }}
- Margin Profile: {{ summary.margin.path or "n/a" }}
- Unit Under Test: {{ summary.unit or "n/a" }}
- Created: {{ summary.created_at }}
- Global Seed: {{ summary.seed }}

## Margin Point Results

{% for sub in subruns -%}
### {{ sub.run_id }}

- Margin Identifier: {{ sub.margin.point_id }}
- Status: {{ sub.status }}
- Duration Seconds: {{ "%.2f"|format(sub.duration_s) }}

| Step | Status | Duration (s) |
|------|--------|--------------|
{% for step in sub.steps -%}
| {{ step.name }} | {{ step.status }} | {{ "%.2f"|format(step.duration_s) }} |
{% endfor %}

{% endfor %}
"""

_DEFAULT_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Road Runner Report - {{ summary.run_id }}</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 2rem; }
      h1, h2, h3 { color: #1f2933; }
      table { border-collapse: collapse; margin-bottom: 1.5rem; width: 100%; }
      th, td { border: 1px solid #d2d6dc; padding: 0.5rem; text-align: left; }
      th { background-color: #f9fafb; }
    </style>
  </head>
  <body>
    <h1>Road Runner Report</h1>
    <section>
      <h2>Run Summary</h2>
      <ul>
        <li><strong>Run ID:</strong> {{ summary.run_id }}</li>
        <li><strong>Flow:</strong> {{ summary.flow.path }}</li>
        <li><strong>Margin Profile:</strong> {{ summary.margin.path or "n/a" }}</li>
        <li><strong>Unit:</strong> {{ summary.unit or "n/a" }}</li>
        <li><strong>Created:</strong> {{ summary.created_at }}</li>
        <li><strong>Global Seed:</strong> {{ summary.seed }}</li>
      </ul>
    </section>
    <section>
      <h2>Margin Point Results</h2>
      {% for sub in subruns %}
      <article>
        <h3>{{ sub.run_id }} ({{ sub.margin.point_id }})</h3>
        <ul>
          <li><strong>Status:</strong> {{ sub.status }}</li>
          <li><strong>Duration (s):</strong> {{ "%.2f"|format(sub.duration_s) }}</li>
        </ul>
        <table>
          <thead>
            <tr>
              <th>Step</th>
              <th>Status</th>
              <th>Duration (s)</th>
            </tr>
          </thead>
          <tbody>
            {% for step in sub.steps %}
            <tr>
              <td>{{ step.name }}</td>
              <td>{{ step.status }}</td>
              <td>{{ "%.2f"|format(step.duration_s) }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </article>
      {% endfor %}
    </section>
  </body>
</html>
"""
