from __future__ import annotations

from pathlib import Path
import sys

import plotly.graph_objects as go
import polars as pl
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from components.dashboard_views import kpi_table
from components.stakeholder_controls import select_context
from core.cost_effectiveness import DEFAULT_WEIGHTS, build_ranking, load_strategy_proxy
from core.metrics import comparison_snapshot, diagnostics_table, metric_delta_label, scenario_delta_table
from core.sample_outputs import latest_sample_run, sample_patient_journeys, sample_run_plots, sample_task_events
from core.scenario_manifest import (
    assumption_delta_rows,
    build_scenario_manifest,
    get_scenario_info,
    scenario_classification,
)


st.set_page_config(page_title="Executive Overview", layout="wide")


def main() -> None:
    st.title("Executive Overview")
    st.caption("NHS clinical pharmacy DES scenario results for managerial comparison.")

    context = select_context()
    if context is None:
        return

    bundle = context.bundle
    baseline = context.baseline
    scenario = context.scenario
    manifest = build_scenario_manifest(bundle.metadata)
    scenario_info = get_scenario_info(manifest, scenario)
    snapshot = comparison_snapshot(
        bundle.summary,
        bundle.waits,
        bundle.utilisation,
        baseline=baseline,
        scenario=scenario,
    )
    ranking = build_ranking(
        bundle.summary,
        baseline=baseline,
        weights=DEFAULT_WEIGHTS,
        strategy_proxy=load_strategy_proxy(context.data_source.strategy_proxy_path),
    )
    selected = _first_row(snapshot, scenario)
    baseline_row = _first_row(snapshot, baseline)
    rank_row = _first_row(ranking, scenario)
    if not selected or not baseline_row:
        st.error("The selected scenario could not be found in this run.")
        return

    _render_decision_line(scenario_info, selected, baseline_row, rank_row)
    _render_key_metrics(selected, baseline_row)
    _render_scenario_results_table(bundle, manifest, ranking, baseline)
    _render_patient_time_chart(selected, baseline_row)
    _render_flow_animation()
    _render_patient_journey(bundle, context.data_source.outputs_root)
    _render_plain_language_interpretation(scenario_info, selected, baseline_row, rank_row)

    st.info(
        "The Scenario Flow Viewer shows how a high-pressure simulated window creates queues, staff handoffs, "
        "and role bottlenecks for the selected assignment rule."
    )

    with st.expander("Scenario assumptions and run status"):
        st.subheader("Selected KPI Table")
        st.dataframe(kpi_table(snapshot, baseline, scenario), width="stretch", hide_index=True)
        st.subheader("Scenario Assumption Changes")
        st.dataframe(
            assumption_delta_rows(bundle.metadata, baseline=baseline, scenario=scenario),
            width="stretch",
            hide_index=True,
        )
        st.subheader("Run Status")
        st.dataframe(
            diagnostics_table(bundle.summary, bundle.queue_lengths, baseline=baseline, scenario=scenario),
            width="stretch",
            hide_index=True,
        )
        st.caption(str(context.run_path))


def _render_decision_line(scenario_info, selected: dict, baseline_row: dict, rank_row: dict) -> None:
    time_delta = _to_float(selected.get("mean_time_in_system_minutes")) - _to_float(
        baseline_row.get("mean_time_in_system_minutes")
    )
    wait_delta = _to_float(selected.get("worst_queue_wait_minutes")) - _to_float(
        baseline_row.get("worst_queue_wait_minutes")
    )
    medrec_delta = (
        _to_float(selected.get("mean_medrec_within_24h_rate"))
        - _to_float(baseline_row.get("mean_medrec_within_24h_rate"))
    ) * 100
    category = rank_row.get("category", "Unclassified") if rank_row else "Unclassified"
    st.markdown(
        f"### {scenario_info.label}\n"
        f"**{scenario_info.family}. {category}.** Compared with baseline: patient time changes by **{time_delta:+.0f} min**, "
        f"worst queue wait changes by **{wait_delta:+.0f} min**, and MedRec within 24h changes by "
        f"**{medrec_delta:+.1f} pp**."
    )
    st.caption(scenario_info.description)


def _render_key_metrics(selected: dict, baseline_row: dict) -> None:
    st.subheader("Key Metrics")
    cols = st.columns(5)
    metrics = [
        ("Mean patient time", "mean_time_in_system_minutes"),
        ("MedRec within 24h", "mean_medrec_within_24h_rate"),
        ("Throughput", "mean_throughput"),
        ("Worst queue wait", "worst_queue_wait_minutes"),
        ("Highest utilisation", "highest_role_utilisation"),
    ]
    for column, (label, key) in zip(cols, metrics):
        delta = _to_float(selected.get(key)) - _to_float(baseline_row.get(key))
        column.metric(
            label,
            metric_delta_label(key, selected.get(key)),
            metric_delta_label(key, delta, is_delta=True),
        )


def _render_scenario_results_table(bundle, manifest: dict, ranking: pl.DataFrame, baseline: str) -> None:
    st.subheader("Scenario Results")
    deltas = scenario_delta_table(bundle.summary, baseline=baseline)
    if deltas.height == 0:
        st.info("No scenario result table was found in this output bundle.")
        return

    rank_rows = {row["scenario"]: row for row in ranking.to_dicts()} if ranking.height else {}
    ordered = sorted(
        deltas.to_dicts(),
        key=lambda row: (
            0 if row.get("scenario") == baseline else 1,
            _to_float(row.get("mean_time_in_system_minutes_delta")),
        ),
    )
    rows = []
    for row in ordered:
        scenario = str(row.get("scenario", ""))
        group = str(row.get("group") or "")
        info = get_scenario_info(manifest, scenario, group)
        rank_row = rank_rows.get(scenario, {})
        rows.append(
            {
                "scenario": info.label,
                "model_id": scenario,
                "family": info.family,
                "mean_time": metric_delta_label(
                    "mean_time_in_system_minutes",
                    row.get("mean_time_in_system_minutes"),
                ),
                "change_vs_baseline": (
                    "baseline"
                    if scenario == baseline
                    else metric_delta_label(
                        "mean_time_in_system_minutes",
                        row.get("mean_time_in_system_minutes_delta"),
                        is_delta=True,
                    )
                ),
                "MedRec_24h": metric_delta_label(
                    "mean_medrec_within_24h_rate",
                    row.get("mean_medrec_within_24h_rate"),
                ),
                "throughput": metric_delta_label("mean_throughput", row.get("mean_throughput")),
                "stability": _friendly_status(row.get("typical_steady_state_status")),
                "managerial_read": rank_row.get("category") or scenario_classification(scenario, group),
            }
        )
    st.dataframe(pl.DataFrame(rows), width="stretch", hide_index=True)
    st.caption(
        "Scenario comparison uses the selected replicated experiment run. Single-run journey visuals explain mechanism, "
        "not the headline scenario ranking."
    )


def _render_patient_time_chart(selected: dict, baseline_row: dict) -> None:
    st.subheader("Patient Time Comparison")
    metrics = ["Mean patient time", "Worst queue wait"]
    fig = go.Figure(
        data=[
            go.Bar(
                name="Baseline",
                x=metrics,
                y=[
                    _to_float(baseline_row.get("mean_time_in_system_minutes")),
                    _to_float(baseline_row.get("worst_queue_wait_minutes")),
                ],
                marker_color="#64748b",
            ),
            go.Bar(
                name="Scenario",
                x=metrics,
                y=[
                    _to_float(selected.get("mean_time_in_system_minutes")),
                    _to_float(selected.get("worst_queue_wait_minutes")),
                ],
                marker_color="#2563eb",
            ),
        ]
    )
    fig.update_layout(
        barmode="group",
        height=340,
        margin={"l": 8, "r": 8, "t": 16, "b": 8},
        yaxis_title="Minutes",
        legend_title_text="",
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _render_flow_animation() -> None:
    st.subheader("Patient Flow Through Pharmacy")
    st.html(
        """
<style>
  .flow {font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 12px 2px 24px;}
  .track {display: grid; grid-template-columns: repeat(8, 1fr); gap: 8px; position: relative; margin-top: 18px;}
  .step {min-height: 58px; border: 1px solid #d6dde5; border-radius: 8px; background: #f8fafc;
         display:flex; align-items:center; justify-content:center; text-align:center; font-size:12px; padding:8px;}
  .patient {position:absolute; top:-18px; left:0; width:18px; height:18px; border-radius:50%; background:#2563eb;
            box-shadow: 0 0 0 7px rgba(37,99,235,.14); animation: travel 10s linear infinite;}
  @keyframes travel {
    0%{left:0%} 13%{left:13%} 26%{left:26%} 39%{left:39%}
    52%{left:52%} 65%{left:65%} 78%{left:78%} 100%{left:calc(100% - 18px)}
  }
  @media (prefers-reduced-motion: reduce) {.patient {animation: none; left:0;}}
</style>
<div class="flow">
  <div class="track">
    <div class="patient"></div>
    <div class="step">Admission</div>
    <div class="step">Drug history</div>
    <div class="step">Medicines reconciliation</div>
    <div class="step">Discrepancy or rework?</div>
    <div class="step">Prescription verification</div>
    <div class="step">Discharge verification</div>
    <div class="step">Counselling?</div>
    <div class="step">Exit</div>
  </div>
</div>
"""
    )


def _render_patient_journey(bundle, outputs_root: Path) -> None:
    st.subheader("Sample Patient Journey")
    policy = (bundle.metadata or {}).get("assignment_policy", "smart_dynamic")
    run_dir = latest_sample_run(policy, outputs_root=outputs_root)
    plots = sample_run_plots(run_dir)
    journeys = sample_patient_journeys(run_dir, limit=8)
    col_plot, col_story = st.columns([1.25, 1])
    with col_plot:
        if "Patient journey sample" in plots:
            st.image(
                str(plots["Patient journey sample"]),
                caption="Example patient journeys from one detailed run",
                width="stretch",
            )
        elif "System animation" in plots:
            st.image(str(plots["System animation"]), caption="Sample system animation", width="stretch")
        else:
            st.info("No sampled journey plot found for this assignment rule.")
    with col_story:
        if journeys.height == 0:
            st.info("No sampled journey output found for this assignment rule.")
            return
        patient_id = int(st.selectbox("Choose a sample patient", journeys["entity_id"].to_list()))
        row = journeys.filter(pl.col("entity_id") == patient_id).to_dicts()[0]
        st.metric("Time in system", f"{_to_float(row.get('time_in_system_minutes')):.0f} min")
        st.metric("Total waiting", f"{_to_float(row.get('total_queue_wait_minutes')):.0f} min")
        st.write("Path:")
        st.write(str(row.get("task_path", "")).replace(" -> ", " -> "))
        with st.expander("Task-level trace"):
            st.dataframe(sample_task_events(run_dir, patient_id), width="stretch", hide_index=True)


def _render_plain_language_interpretation(scenario_info, selected: dict, baseline_row: dict, rank_row: dict) -> None:
    st.subheader("Management Interpretation")
    bottleneck = selected.get("worst_queue_task", "the main queue")
    role = selected.get("highest_utilisation_role", "the highest-pressure role")
    category = rank_row.get("category", "an exploratory option") if rank_row else "an exploratory option"
    st.write(
        f"This scenario is best read as **{category}** in the **{scenario_info.family.lower()}** family. "
        f"The main visible bottleneck is **{bottleneck}**, and the highest-pressure staff group is **{role}**. "
        f"{scenario_info.caveat}"
    )


def _first_row(frame: pl.DataFrame, scenario: str) -> dict:
    if "scenario" not in frame.columns:
        return {}
    match = frame.filter(pl.col("scenario") == scenario)
    return match.to_dicts()[0] if match.height else {}


def _to_float(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _friendly_status(value) -> str:
    text = str(value or "unknown").replace("_", " ")
    if "not steady" in text:
        return "Not steady"
    if "closest" in text:
        return "Closest to steady state"
    if "steady" in text:
        return "Approximately steady"
    return text.title()


if __name__ == "__main__":
    main()
