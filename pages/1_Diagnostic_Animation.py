from __future__ import annotations

from pathlib import Path
import sys

import plotly.graph_objects as go
import polars as pl
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from components.diagnostic_animation import render_window_animation
from components.stakeholder_controls import select_context
from core.sample_outputs import daily_kpis, latest_sample_run, role_activity_window, task_events_window, window_summary


st.set_page_config(page_title="Diagnostic Animation", layout="wide")


METRIC_OPTIONS = {
    "Mean backlog": "mean_total_backlog",
    "Mean queue wait": "mean_queue_wait_minutes",
    "Mean patient time": "mean_time_in_system_minutes",
    "MedRec within 24h": "medrec_within_24h_rate",
    "Arrivals": "arrivals_all",
    "Completions": "completions_all",
}


POLICY_GUIDE = {
    "priority": (
        "Fixed priority",
        "Staff check eligible queues in a fixed task order, then take the oldest patient in that queue.",
    ),
    "dynamic": (
        "Queue pressure",
        "Staff choose the eligible queue with the largest visible backlog, then longest wait, then fixed priority.",
    ),
    "smart_dynamic": (
        "Role-aware pressure",
        "Staff choose from visible eligible queues, respect named-worker independence, then use role-specific bottleneck tie-breaks.",
    ),
    "random": (
        "Random control",
        "Staff choose uniformly from eligible non-empty queues. This is a comparison case, not a recommended operating rule.",
    ),
}


def main() -> None:
    st.title("Diagnostic Animation")
    st.caption("Pick a KPI spike, then inspect the patient and staff interactions inside that simulated window.")

    context = select_context()
    if context is None:
        return

    policy = (context.bundle.metadata or {}).get("assignment_policy", "smart_dynamic")
    run_dir = latest_sample_run(str(policy), outputs_root=context.data_source.outputs_root)
    if run_dir is None:
        st.info("No detailed event-log run was found for this assignment policy.")
        return

    st.caption(f"Detailed event-log sample: {run_dir}")
    _render_window_investigation(run_dir)
    _render_conceptual_model()
    _render_policy_guide(str(policy))


def _render_window_investigation(run_dir: Path) -> None:
    kpis = daily_kpis(run_dir)
    if kpis.height == 0:
        st.info("No detailed KPI time-series output found for interactive window investigation.")
        return

    metric_label, metric, start_day, end_day, peak_day = _window_controls(kpis)
    _render_kpi_chart(kpis, metric_label, metric, start_day, end_day, peak_day)

    summary = window_summary(run_dir, start_day=start_day, end_day=end_day)
    _render_window_metrics(summary)

    events = task_events_window(run_dir, start_day=start_day, end_day=end_day, limit=36)
    roles = role_activity_window(run_dir, start_day=start_day, end_day=end_day)

    st.subheader("Patient And Staff Interactions In This Window")
    st.write(
        "Each patient task appears first as queue waiting time, then as a staff interaction. "
        "Red queue bars point to long waits; coloured staff bars show which role picked up the work."
    )
    render_window_animation(events, start_day=start_day, end_day=end_day)

    _render_diagnostic_read(events, roles, summary)

    with st.expander("Raw trace for analysts"):
        st.dataframe(events, width="stretch", hide_index=True)
        st.dataframe(roles, width="stretch", hide_index=True)


def _window_controls(kpis: pl.DataFrame) -> tuple[str, str, int, int, int]:
    control_metric, control_window = st.columns([1, 2])
    with control_metric:
        metric_label = st.selectbox("KPI to inspect", list(METRIC_OPTIONS), index=0)
    metric = METRIC_OPTIONS[metric_label]

    counted = kpis.filter(pl.col("is_counted_period") == True) if "is_counted_period" in kpis.columns else kpis
    if counted.height == 0:
        counted = kpis
    min_day = int(counted["day_index"].min())
    max_day = int(counted["day_index"].max())
    peak_frame = counted.select(["day_index", metric]).drop_nulls()
    peak_day = int(peak_frame.sort(metric, descending=True)["day_index"][0]) if peak_frame.height else min_day
    default_start = max(min_day, peak_day - 3)
    default_end = min(max_day, peak_day + 4)

    with control_window:
        if min_day == max_day:
            start_day = end_day = min_day
            st.write(f"Selected simulated day: {min_day}")
        else:
            start_day, end_day = st.slider(
                "Time window by simulated day",
                min_value=min_day,
                max_value=max_day,
                value=(default_start, default_end),
            )
    return metric_label, metric, int(start_day), int(end_day), peak_day


def _render_kpi_chart(
    kpis: pl.DataFrame,
    metric_label: str,
    metric: str,
    start_day: int,
    end_day: int,
    peak_day: int,
) -> None:
    chart_frame = kpis.select(["day_index", metric]).rename({metric: metric_label}).drop_nulls()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=chart_frame["day_index"].to_list(),
            y=chart_frame[metric_label].to_list(),
            mode="lines",
            line={"color": "#2563eb", "width": 2},
            name=metric_label,
        )
    )
    fig.add_vrect(
        x0=start_day,
        x1=end_day,
        fillcolor="#f59e0b",
        opacity=0.18,
        line_width=0,
        annotation_text="selected window",
        annotation_position="top left",
    )
    fig.add_vline(x=peak_day, line_width=1, line_dash="dot", line_color="#dc2626")
    fig.update_layout(
        height=320,
        margin={"l": 8, "r": 8, "t": 28, "b": 8},
        xaxis_title="Simulated day",
        yaxis_title=metric_label,
        showlegend=False,
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption(
        f"Selected window: simulated days {start_day} to {end_day}. "
        f"The dotted marker shows the largest visible {metric_label.lower()} spike."
    )


def _render_window_metrics(summary: dict[str, float]) -> None:
    if not summary:
        return
    cols = st.columns(5)
    cols[0].metric("Arrivals", f"{summary['arrivals']:.0f}")
    cols[1].metric("Completions", f"{summary['completions']:.0f}")
    cols[2].metric("Net flow", f"{summary['net_flow']:+.0f}")
    cols[3].metric("Mean backlog", f"{summary['mean_backlog']:.0f}")
    cols[4].metric("Mean wait", f"{summary['mean_queue_wait']:.0f} min")


def _render_diagnostic_read(events: pl.DataFrame, roles: pl.DataFrame, summary: dict[str, float]) -> None:
    st.subheader("What To Look For")
    col_story, col_roles = st.columns([1.3, 1])
    with col_story:
        st.write(_diagnostic_sentence(summary, events))
        longest = _long_wait_events(events)
        if longest:
            st.write("Longest waits in the window:")
            for item in longest:
                st.markdown(f"- **P{item['patient']}** waited **{item['wait']:.0f} min** for {item['task']}.")
    with col_roles:
        if roles.height == 0:
            st.info("No staff utilisation trace found for this window.")
            return
        for row in roles.head(3).to_dicts():
            st.metric(
                str(row.get("worker_role", "staff")).title(),
                f"{_safe_float(row.get('mean_utilisation')) * 100:.0f}% utilised",
                f"{_safe_float(row.get('busy_minutes')) / 60:.1f} busy hours",
            )


def _diagnostic_sentence(summary: dict[str, float], events: pl.DataFrame) -> str:
    if not summary:
        return "Use the red queue bars and staff-role lanes to see whether patients waited before eligible staff picked up work."
    net_flow = _safe_float(summary.get("net_flow"))
    mean_wait = _safe_float(summary.get("mean_queue_wait"))
    long_waits = 0
    if events.height and "queue_wait_minutes" in events.columns:
        long_waits = events.filter(pl.col("queue_wait_minutes") >= 240).height
    flow_text = "arrivals exceeded completions" if net_flow > 0 else "completions kept pace with arrivals"
    wait_text = "long waits are visible" if long_waits else "long waits are not dominant in the sampled trace"
    return (
        f"In this selected window, {flow_text}. Mean queue wait is about {mean_wait:.0f} minutes, "
        f"and {wait_text}. If the chart spike is real operational pressure, it should appear as red queue "
        "segments clustering before one or more staff-role lanes."
    )


def _long_wait_events(events: pl.DataFrame) -> list[dict]:
    if events.height == 0 or "queue_wait_minutes" not in events.columns:
        return []
    rows = events.sort("queue_wait_minutes", descending=True).head(5).to_dicts()
    return [
        {
            "patient": row.get("entity_id", "?"),
            "task": str(row.get("task_name", "task")).replace("_", " "),
            "wait": _safe_float(row.get("queue_wait_minutes")),
        }
        for row in rows
    ]


def _render_conceptual_model() -> None:
    with st.expander("Conceptual Process Map Used By The Animation", expanded=True):
        st.graphviz_chart(
            """
digraph {
  graph [rankdir=LR, splines=true]
  node [shape=box, style="rounded,filled", fillcolor="#f8fafc", fontname="Helvetica"]
  edge [fontname="Helvetica"]

  admit [label="Patient admitted\\n24/7 arrivals", fillcolor="#eef4fb"]
  drug [label="Drug history\\nMMPT/CPT or junior", fillcolor="#e8f3e8"]
  low [label="Low risk?\\n30%", shape=diamond, fillcolor="#fff7d6"]
  medrec [label="Medicines reconciliation\\nMMPT/CPT, junior, senior", fillcolor="#e8f3e8"]
  discrepancy [label="Upstream discrepancy?\\n60%", shape=diamond, fillcolor="#fff7d6"]
  resolve_up [label="Resolve upstream discrepancy\\njunior or senior", fillcolor="#e8f3e8"]
  diagnosis [label="Diagnosis/treatment planning\\nexternal, not timed", fillcolor="#f1f1f1"]
  verify_rx [label="Prescription verification\\njunior or senior", fillcolor="#e8f3e8"]
  writer [label="Who writes discharge?\\n44% pharmacy / 56% medic", shape=diamond, fillcolor="#fff7d6"]
  write_rx [label="Write discharge prescription\\nsenior only", fillcolor="#e8f3e8"]
  medic_write [label="Medic writes prescription\\noutside pharmacy capacity", fillcolor="#f1f1f1"]
  discharge_verify [label="Verify discharge prescription\\njunior, senior, or CPU B CPT", fillcolor="#e8f3e8"]
  medic_error [label="Medic-written error?\\n20% if medic-written", shape=diamond, fillcolor="#fff7d6"]
  resolve_error [label="Resolve medic prescription error\\njunior or senior", fillcolor="#e8f3e8"]
  counsel [label="Counselling needed?\\n35%", shape=diamond, fillcolor="#fff7d6"]
  counsel_task [label="Counsel patient\\nMMPT/CPT, junior, senior", fillcolor="#e8f3e8"]
  exit [label="Exit modelled pathway", fillcolor="#eef4fb"]

  admit -> drug -> low
  low -> exit [label="yes"]
  low -> medrec [label="no"]
  medrec -> discrepancy
  discrepancy -> resolve_up [label="yes"]
  discrepancy -> diagnosis [label="no"]
  resolve_up -> diagnosis
  diagnosis -> verify_rx -> writer
  writer -> write_rx [label="pharmacy"]
  writer -> medic_write [label="medic"]
  write_rx -> discharge_verify
  medic_write -> discharge_verify
  discharge_verify -> medic_error
  medic_error -> resolve_error [label="yes"]
  resolve_error -> discharge_verify [label="different verifier"]
  medic_error -> counsel [label="no"]
  counsel -> counsel_task [label="yes"]
  counsel -> exit [label="no"]
  counsel_task -> exit
}
""",
            width="stretch",
        )
        st.write(
            "Patients remain a single entity. The animation shows the operational part of this map: "
            "a task enters a visible queue, an eligible staff member starts it, and the patient then moves to the next pathway step."
        )


def _render_policy_guide(selected_policy: str) -> None:
    st.subheader("Assignment Policy Guide")
    cols = st.columns(4)
    for column, key in zip(cols, ["priority", "dynamic", "smart_dynamic", "random"]):
        title, body = POLICY_GUIDE[key]
        label = f"{key}: {title}"
        if key == selected_policy:
            label = f"Selected - {label}"
        column.markdown(f"**{label}**")
        column.write(body)


def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    main()
