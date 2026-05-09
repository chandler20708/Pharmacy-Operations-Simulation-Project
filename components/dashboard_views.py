from __future__ import annotations

import polars as pl
import streamlit as st

from core.cost_effectiveness import build_ranking
from core.metrics import (
    comparison_snapshot,
    delta_color,
    metric_delta_label,
    metric_interpretation,
)
from core.scenario_manifest import get_scenario_info


def ranking_frame(ctx) -> pl.DataFrame:
    return build_ranking(
        ctx.bundle.summary,
        baseline=ctx.baseline,
        weights=ctx.weights,
        strategy_proxy=ctx.strategy_proxy,
    )


def snapshot_frame(ctx) -> pl.DataFrame:
    return comparison_snapshot(
        ctx.bundle.summary,
        ctx.bundle.waits,
        ctx.bundle.utilisation,
        baseline=ctx.baseline,
        scenario=ctx.scenario,
    )


def render_decision_snapshot(ctx) -> tuple[pl.DataFrame, pl.DataFrame]:
    ranking = ranking_frame(ctx)
    snapshot = snapshot_frame(ctx)
    selected = snapshot.filter(snapshot["scenario"] == ctx.scenario).to_dicts()[0]
    baseline_row = snapshot.filter(snapshot["scenario"] == ctx.baseline).to_dicts()[0]
    rank_row = ranking.filter(pl.col("scenario") == ctx.scenario).to_dicts()[0]
    scenario_info = get_scenario_info(ctx.manifest, ctx.scenario, selected.get("group"))
    category = rank_row.get("category", "Unclassified")
    wait_delta = _to_float(selected.get("worst_queue_wait_minutes")) - _to_float(
        baseline_row.get("worst_queue_wait_minutes")
    )
    st.subheader("Decision Snapshot")
    st.markdown(
        f"**{category}: {scenario_info.label}.** "
        f"Mean time changes by {metric_delta_label('mean_time_in_system_minutes', selected.get('mean_time_in_system_minutes_delta'), is_delta=True)}, "
        f"MedRec within 24h changes by {metric_delta_label('mean_medrec_within_24h_rate', selected.get('mean_medrec_within_24h_rate_delta'), is_delta=True)}, "
        f"and worst queue wait changes by {wait_delta:+.0f} min."
    )
    cols = st.columns(5)
    _metric(cols[0], "Mean time", selected, "mean_time_in_system_minutes")
    _metric(cols[1], "MedRec 24h", selected, "mean_medrec_within_24h_rate")
    _metric(cols[2], "Throughput", selected, "mean_throughput")
    _metric(cols[3], "Worst wait", selected, "worst_queue_wait_minutes")
    _metric(cols[4], "Highest utilisation", selected, "highest_role_utilisation")
    st.caption(scenario_info.caveat)
    return ranking, snapshot


def kpi_table(snapshot: pl.DataFrame, baseline: str, scenario: str) -> pl.DataFrame:
    rows = {row["scenario"]: row for row in snapshot.to_dicts()}
    base = rows[baseline]
    selected = rows[scenario]
    metrics = [
        ("mean_throughput", "Throughput", ""),
        ("mean_eventual_completion_rate", "Eventual completion", "%"),
        ("mean_time_in_system_minutes", "Mean time in system", "minutes"),
        ("mean_medrec_within_24h_rate", "MedRec within 24h", "%"),
        ("mean_traffic_intensity_proxy", "Traffic intensity", ""),
        ("worst_queue_wait_minutes", "Worst queue wait", "minutes"),
        ("highest_role_utilisation", "Highest role utilisation", "%"),
    ]
    table = []
    for key, label, unit in metrics:
        delta = _to_float(selected.get(key)) - _to_float(base.get(key))
        table.append(
            {
                "metric": label,
                "baseline": metric_delta_label(key, base.get(key)),
                "scenario": metric_delta_label(key, selected.get(key)),
                "change": metric_delta_label(key, delta, is_delta=True),
                "interpretation": metric_interpretation(key, delta),
                "unit": unit,
            }
        )
    return pl.DataFrame(table)


def bottleneck_story(snapshot: pl.DataFrame, baseline: str, scenario: str) -> pl.DataFrame:
    rows = {row["scenario"]: row for row in snapshot.to_dicts()}
    base = rows[baseline]
    selected = rows[scenario]
    return pl.DataFrame(
        [
            {
                "signal": "Worst queue task",
                "baseline": base.get("worst_queue_task"),
                "scenario": selected.get("worst_queue_task"),
                "change": "moved" if base.get("worst_queue_task") != selected.get("worst_queue_task") else "same bottleneck",
            },
            {
                "signal": "Worst queue wait",
                "baseline": metric_delta_label("worst_queue_wait_minutes", base.get("worst_queue_wait_minutes")),
                "scenario": metric_delta_label("worst_queue_wait_minutes", selected.get("worst_queue_wait_minutes")),
                "change": metric_delta_label(
                    "worst_queue_wait_minutes",
                    _to_float(selected.get("worst_queue_wait_minutes")) - _to_float(base.get("worst_queue_wait_minutes")),
                    is_delta=True,
                ),
            },
            {
                "signal": "Highest-pressure role",
                "baseline": base.get("highest_utilisation_role"),
                "scenario": selected.get("highest_utilisation_role"),
                "change": "moved" if base.get("highest_utilisation_role") != selected.get("highest_utilisation_role") else "same role",
            },
        ]
    )


def _metric(column, label: str, row: dict, metric: str) -> None:
    value = row.get(metric)
    delta = row.get(f"{metric}_delta")
    column.metric(
        label,
        metric_delta_label(metric, value),
        metric_delta_label(metric, delta, is_delta=True),
        delta_color=delta_color(metric),
    )


def _to_float(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
