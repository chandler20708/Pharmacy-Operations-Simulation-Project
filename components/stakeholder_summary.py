from __future__ import annotations

import polars as pl

from core.metrics import select_scenario


def build_summary(
    summary: pl.DataFrame,
    ranking: pl.DataFrame,
    *,
    baseline: str,
    scenario: str,
    scenario_label: str | None = None,
    scenario_family: str | None = None,
    scenario_description: str | None = None,
    scenario_caveat: str | None = None,
    assumption_rows: list[dict] | None = None,
    snapshot: pl.DataFrame | None = None,
    metadata: dict | None = None,
) -> str:
    base = select_scenario(summary, baseline)
    row = select_scenario(summary, scenario)
    rank_row = select_scenario(ranking, scenario)
    if not row:
        return "Select a scenario to generate a stakeholder summary."

    time_delta = _to_float(row.get("mean_time_in_system_minutes")) - _to_float(
        base.get("mean_time_in_system_minutes")
    )
    medrec_delta = (
        _to_float(row.get("mean_medrec_within_24h_rate"))
        - _to_float(base.get("mean_medrec_within_24h_rate"))
    ) * 100
    throughput_delta = _to_float(row.get("mean_throughput")) - _to_float(
        base.get("mean_throughput")
    )
    category = rank_row.get("category", "Unclassified")
    implementation_score = rank_row.get("implementation_score", "n/a")
    governance_risk = rank_row.get("governance_risk", "n/a")
    cost_proxy = rank_row.get("cost_proxy", "Proxy assumptions unavailable")
    bottleneck_text = _bottleneck_text(snapshot, baseline, scenario)
    run_text = _run_text(metadata)
    what_changed = _what_changed(assumption_rows)
    return (
        f"# Scenario: {scenario_label or scenario}\n\n"
        f"Model ID: `{scenario}`\n\n"
        f"Family: {scenario_family or row.get('group', 'Unknown')}\n\n"
        f"## What changed\n\n"
        f"{scenario_description or 'No exported scenario description available.'}\n\n"
        f"{what_changed}\n\n"
        f"## KPI movement vs baseline\n\n"
        f"- Mean time in system: {time_delta:+.0f} minutes\n"
        f"- MedRec within 24h: {medrec_delta:+.2f} percentage points\n"
        f"- Throughput: {throughput_delta:+.3f}\n\n"
        f"## Bottleneck movement\n\n"
        f"{bottleneck_text}\n\n"
        f"## Cost and feasibility\n\n"
        f"- Category: {category}\n"
        f"- Implementation score: {implementation_score}\n"
        f"- Governance risk: {governance_risk}\n"
        f"- Cost proxy: {cost_proxy}\n\n"
        f"## Evidence basis\n\n"
        f"{run_text}\n\n"
        f"## Caveats\n\n"
        f"{scenario_caveat or 'Review operational feasibility before acting.'} "
        "The ranking is conditional on the selected KPI weights and proxy "
        "implementation-cost assumptions. It is a decision aid, not financial ROI."
    )


def _to_float(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bottleneck_text(snapshot: pl.DataFrame | None, baseline: str, scenario: str) -> str:
    if snapshot is None or snapshot.height == 0 or "worst_queue_task" not in snapshot.columns:
        return "Bottleneck comparison was not available for this output bundle."
    rows = {row["scenario"]: row for row in snapshot.to_dicts()}
    base = rows.get(baseline, {})
    selected = rows.get(scenario, {})
    return (
        f"Worst queue changes from {base.get('worst_queue_task', 'n/a')} "
        f"({ _to_float(base.get('worst_queue_wait_minutes')):.0f} min) to "
        f"{selected.get('worst_queue_task', 'n/a')} "
        f"({ _to_float(selected.get('worst_queue_wait_minutes')):.0f} min). "
        f"Highest-pressure role changes from {base.get('highest_utilisation_role', 'n/a')} "
        f"to {selected.get('highest_utilisation_role', 'n/a')}."
    )


def _run_text(metadata: dict | None) -> str:
    if not metadata:
        return "Run metadata was not available; verify assignment policy and replication design before use."
    return (
        f"Assignment rule `{metadata.get('assignment_policy', 'unknown')}`, "
        f"{metadata.get('replications', '?')} replications, "
        f"{metadata.get('warmup_days', '?')} warm-up days, "
        f"{metadata.get('counted_days', '?')} counted days, "
        f"{metadata.get('drain_days', '?')} drain days. "
        f"Created at {metadata.get('created_at', 'unknown')}."
    )


def _what_changed(rows: list[dict] | None) -> str:
    if not rows:
        return "No assumption-delta table was available."
    changed = [row for row in rows if row.get("note") != "unchanged"]
    if not changed:
        return "No exported baseline assumption changes were detected."
    bullets = [
        f"- {row.get('field')}: {row.get('baseline')} -> {row.get('scenario')} ({row.get('note')})"
        for row in changed[:6]
    ]
    return "\n".join(bullets)
