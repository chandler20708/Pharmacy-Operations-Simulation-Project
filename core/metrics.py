from __future__ import annotations

from dataclasses import dataclass

import polars as pl


BASELINE_SCENARIO = "A1_baseline"

HEADLINE_METRICS = {
    "mean_throughput": "Throughput",
    "mean_eventual_completion_rate": "Eventual completion",
    "mean_time_in_system_minutes": "Mean time in system",
    "mean_medrec_within_24h_rate": "MedRec within 24h",
    "mean_late_window_net_flow_per_day": "Late net flow/day",
    "mean_traffic_intensity_proxy": "Traffic intensity",
}

LOWER_IS_BETTER = {
    "mean_time_in_system_minutes",
    "mean_late_window_relative_flow_imbalance",
    "mean_traffic_intensity_proxy",
    "mean_weekly_people_in_system_slope_per_day",
}


@dataclass(frozen=True)
class Bottleneck:
    scenario: str
    task_name: str
    mean_queue_wait_minutes: float


@dataclass(frozen=True)
class RolePressure:
    scenario: str
    worker_role: str
    mean_utilisation: float


def select_scenario(summary: pl.DataFrame, scenario: str) -> dict:
    frame = summary.filter(pl.col("scenario") == scenario)
    return frame.to_dicts()[0] if frame.height else {}


def scenario_delta_table(
    summary: pl.DataFrame,
    *,
    baseline: str = BASELINE_SCENARIO,
) -> pl.DataFrame:
    if summary.height == 0:
        return pl.DataFrame()
    baseline_row = select_scenario(summary, baseline)
    rows: list[dict] = []
    for row in summary.to_dicts():
        item = {
            "group": row.get("group"),
            "scenario": row.get("scenario"),
            "typical_steady_state_status": row.get("typical_steady_state_status"),
        }
        for metric in HEADLINE_METRICS:
            value = _to_float(row.get(metric))
            base_value = _to_float(baseline_row.get(metric))
            item[metric] = value
            item[f"{metric}_delta"] = value - base_value
        rows.append(item)
    return pl.DataFrame(rows)


def worst_bottlenecks(waits: pl.DataFrame | None) -> pl.DataFrame:
    if waits is None or waits.height == 0:
        return pl.DataFrame()
    return (
        waits.sort(["scenario", "mean_queue_wait_minutes"], descending=[False, True])
        .group_by("scenario", maintain_order=True)
        .first()
        .select(["group", "scenario", "task_name", "mean_queue_wait_minutes"])
    )


def highest_role_utilisation(utilisation: pl.DataFrame | None) -> pl.DataFrame:
    if utilisation is None or utilisation.height == 0:
        return pl.DataFrame()
    return (
        utilisation.sort(["scenario", "mean_utilisation"], descending=[False, True])
        .group_by("scenario", maintain_order=True)
        .first()
        .select(["group", "scenario", "worker_role", "mean_utilisation"])
    )


def comparison_snapshot(
    summary: pl.DataFrame,
    waits: pl.DataFrame | None,
    utilisation: pl.DataFrame | None,
    *,
    baseline: str,
    scenario: str,
) -> pl.DataFrame:
    deltas = scenario_delta_table(summary, baseline=baseline)
    bottlenecks = worst_bottlenecks(waits)
    roles = highest_role_utilisation(utilisation)

    selected = deltas.filter(pl.col("scenario").is_in([baseline, scenario]))
    if bottlenecks.height:
        selected = selected.join(
            bottlenecks.select(
                ["scenario", "task_name", "mean_queue_wait_minutes"]
            ).rename(
                {
                    "task_name": "worst_queue_task",
                    "mean_queue_wait_minutes": "worst_queue_wait_minutes",
                }
            ),
            on="scenario",
            how="left",
        )
    if roles.height:
        selected = selected.join(
            roles.select(["scenario", "worker_role", "mean_utilisation"]).rename(
                {
                    "worker_role": "highest_utilisation_role",
                    "mean_utilisation": "highest_role_utilisation",
                }
            ),
            on="scenario",
            how="left",
        )
    selected = _add_joined_metric_delta(
        selected,
        baseline=baseline,
        metric="worst_queue_wait_minutes",
    )
    selected = _add_joined_metric_delta(
        selected,
        baseline=baseline,
        metric="highest_role_utilisation",
    )
    return selected


def metric_delta_label(
    metric: str,
    value: float | int | None,
    *,
    is_delta: bool = False,
) -> str:
    if value is None:
        return "n/a"
    if metric.endswith("_rate") or "completion_rate" in metric:
        return f"{value * 100:.1f}%" if not is_delta else f"{value * 100:+.1f} pp"
    if "utilisation" in metric:
        return f"{value * 100:.1f}%" if not is_delta else f"{value * 100:+.1f} pp"
    if "minutes" in metric:
        return f"{value:+.0f} min" if is_delta else f"{value:.0f} min"
    return f"{value:+.2f}" if is_delta else f"{value:.2f}"


def delta_color(metric: str) -> str:
    return "inverse" if metric in LOWER_IS_BETTER or "wait" in metric else "normal"


def metric_interpretation(metric: str, delta: float | int | None) -> str:
    if delta is None:
        return "No comparison available"
    value = _to_float(delta)
    if abs(value) < 1e-9:
        return "No material change"
    improvement = value < 0 if metric in LOWER_IS_BETTER or "wait" in metric else value > 0
    return "Improved" if improvement else "Worse"


def top_n_waits(waits: pl.DataFrame | None, scenario: str, n: int = 3) -> pl.DataFrame:
    if waits is None or waits.height == 0:
        return pl.DataFrame()
    return (
        waits.filter(pl.col("scenario") == scenario)
        .sort("mean_queue_wait_minutes", descending=True)
        .head(n)
    )


def top_n_roles(utilisation: pl.DataFrame | None, scenario: str, n: int = 3) -> pl.DataFrame:
    if utilisation is None or utilisation.height == 0:
        return pl.DataFrame()
    return (
        utilisation.filter(pl.col("scenario") == scenario)
        .sort("mean_utilisation", descending=True)
        .head(n)
    )


def diagnostics_table(summary: pl.DataFrame, queue_lengths: pl.DataFrame | None, *, baseline: str, scenario: str) -> pl.DataFrame:
    rows = []
    selected = {row["scenario"]: row for row in summary.filter(pl.col("scenario").is_in([baseline, scenario])).to_dicts()}
    metrics = [
        ("typical_steady_state_status", "Steady-state status", ""),
        ("mean_late_window_net_flow_per_day", "Late net flow", "patients/day"),
        ("mean_late_window_relative_flow_imbalance", "Late flow imbalance", ""),
        ("mean_traffic_intensity_proxy", "Traffic intensity", ""),
        ("mean_weekly_people_in_system_slope_per_day", "Weekly people-in-system slope", "patients/day"),
    ]
    for key, label, unit in metrics:
        base = selected.get(baseline, {}).get(key)
        value = selected.get(scenario, {}).get(key)
        rows.append({"signal": label, "baseline": base, "scenario": value, "unit": unit})
    if queue_lengths is not None and queue_lengths.height:
        for name, label in (("mean_queue_length", "Mean visible queue length"), ("mean_max_queue_length", "Mean max visible queue length")):
            base_value = _max_queue_metric(queue_lengths, baseline, name)
            scenario_value = _max_queue_metric(queue_lengths, scenario, name)
            rows.append({"signal": label, "baseline": base_value, "scenario": scenario_value, "unit": "patients"})
    return pl.DataFrame(rows)


def steady_state_interpretation(summary: pl.DataFrame, *, scenario: str) -> dict[str, str]:
    row = select_scenario(summary, scenario)
    status = str(row.get("typical_steady_state_status", "unknown"))
    net_flow = _to_float(row.get("mean_late_window_net_flow_per_day"))
    imbalance = abs(_to_float(row.get("mean_late_window_relative_flow_imbalance")))
    traffic = _to_float(row.get("mean_traffic_intensity_proxy"))
    slope = _to_float(row.get("mean_weekly_people_in_system_slope_per_day"))

    if "not" in status.lower():
        report_use = "treat cautiously"
    elif "closest" in status.lower() or "steady" in status.lower():
        report_use = "acceptable scenario evidence"
    else:
        report_use = "review run status before report use"

    return {
        "selected_scenario": scenario,
        "status": status,
        "late_flow_balance": _flow_balance_label(net_flow, imbalance),
        "traffic_intensity": _traffic_label(traffic),
        "backlog_signal": _backlog_label(slope),
        "report_use": report_use,
    }


def _max_queue_metric(queue_lengths: pl.DataFrame, scenario: str, column: str) -> float | None:
    frame = queue_lengths.filter(pl.col("scenario") == scenario)
    if frame.height == 0 or column not in frame.columns:
        return None
    return float(frame[column].max())


def _flow_balance_label(net_flow: float, imbalance: float) -> str:
    if imbalance <= 0.02 and abs(net_flow) <= 0.5:
        return "balanced"
    if net_flow > 0:
        return "arrivals exceed completions"
    if net_flow < 0:
        return "completions exceed arrivals"
    return "unclear"


def _traffic_label(traffic: float) -> str:
    if traffic >= 1.03:
        return "overloaded"
    if traffic >= 0.97:
        return "near capacity"
    if traffic > 0:
        return "underloaded"
    return "unknown"


def _backlog_label(slope: float) -> str:
    if slope > 0.05:
        return "worsening"
    if slope < -0.05:
        return "improving"
    return "broadly flat"


def _add_joined_metric_delta(
    frame: pl.DataFrame,
    *,
    baseline: str,
    metric: str,
) -> pl.DataFrame:
    if metric not in frame.columns:
        return frame
    base = frame.filter(pl.col("scenario") == baseline)
    if base.height == 0:
        return frame.with_columns(pl.lit(None).alias(f"{metric}_delta"))
    base_value = base[metric][0]
    if base_value is None:
        return frame.with_columns(pl.lit(None).alias(f"{metric}_delta"))
    return frame.with_columns((pl.col(metric) - float(base_value)).alias(f"{metric}_delta"))


def _to_float(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
