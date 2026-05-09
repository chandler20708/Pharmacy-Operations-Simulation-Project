from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from app.core.cost_effectiveness import DEFAULT_WEIGHTS, load_strategy_proxy
from app.core.data_loader import (
    ScenarioOutputBundle,
    discover_scenario_runs,
    load_run,
    load_run_metadata,
    run_display_label,
    scenario_names,
)
from app.core.scenario_manifest import (
    build_scenario_manifest,
    scenario_options_with_labels,
)


WEIGHT_PRESETS = {
    "Balanced": DEFAULT_WEIGHTS,
    "Delay-focused": {
        "time_in_system": 0.55,
        "medrec_24h": 0.20,
        "throughput": 0.10,
        "traffic_intensity": 0.10,
        "steady_state": 0.05,
    },
    "Service-target-focused": {
        "time_in_system": 0.20,
        "medrec_24h": 0.50,
        "throughput": 0.10,
        "traffic_intensity": 0.05,
        "steady_state": 0.15,
    },
    "Cost-sensitive": {
        "time_in_system": 0.25,
        "medrec_24h": 0.20,
        "throughput": 0.10,
        "traffic_intensity": 0.20,
        "steady_state": 0.25,
    },
}


@dataclass(frozen=True)
class AppContext:
    bundle: ScenarioOutputBundle
    baseline: str
    scenario: str
    weights: dict[str, float]
    manifest: dict
    strategy_proxy: object
    run_path: str


@st.cache_data(show_spinner=False)
def _load_run(run_dir: str) -> ScenarioOutputBundle:
    return load_run(run_dir)


@st.cache_data(show_spinner=False)
def _metadata(run_dir: str) -> dict | None:
    return load_run_metadata(run_dir)


def render_sidebar() -> AppContext | None:
    runs = discover_scenario_runs()
    if not runs:
        st.sidebar.error("No scenario experiment outputs found.")
        return None

    run_values = [str(path) for path in runs]
    metadata_by_run = {value: _metadata(value) for value in run_values}
    policies = ["Any"] + sorted(
        {
            str(metadata.get("assignment_policy"))
            for metadata in metadata_by_run.values()
            if metadata and metadata.get("assignment_policy")
        }
    )

    st.sidebar.header("Run")
    selected_policy = st.sidebar.selectbox(
        "Assignment policy",
        options=policies,
        index=policies.index("smart_dynamic") if "smart_dynamic" in policies else 0,
    )
    filtered = [
        value
        for value in run_values
        if selected_policy == "Any"
        or (metadata_by_run.get(value) or {}).get("assignment_policy") == selected_policy
    ]
    selected_run = st.sidebar.selectbox(
        "Scenario output",
        options=filtered,
        format_func=lambda value: run_display_label(Path(value), metadata_by_run.get(value)),
        index=0,
    )
    bundle = _load_run(selected_run)
    _run_provenance(bundle.metadata, selected_run)

    manifest = build_scenario_manifest(bundle.metadata)
    names = scenario_names(bundle.summary)
    labels = scenario_options_with_labels(names, manifest)
    baseline = st.sidebar.selectbox(
        "Baseline",
        options=names,
        format_func=lambda value: labels.get(value, value),
        index=names.index("A1_baseline") if "A1_baseline" in names else 0,
    )
    scenario_options = [name for name in names if name != baseline] or names
    scenario = st.sidebar.selectbox(
        "Scenario",
        options=scenario_options,
        format_func=lambda value: labels.get(value, value),
        index=0,
    )

    st.sidebar.header("Ranking")
    preset = st.sidebar.selectbox("Weight preset", options=list(WEIGHT_PRESETS), index=0)
    st.sidebar.caption("Weights are normalized automatically.")
    base_weights = WEIGHT_PRESETS[preset]
    with st.sidebar.expander("Advanced KPI weights"):
        weights = {
            "time_in_system": st.slider("Mean time", 0.0, 1.0, base_weights["time_in_system"], 0.05),
            "medrec_24h": st.slider("MedRec 24h", 0.0, 1.0, base_weights["medrec_24h"], 0.05),
            "throughput": st.slider("Throughput", 0.0, 1.0, base_weights["throughput"], 0.05),
            "traffic_intensity": st.slider("Traffic intensity", 0.0, 1.0, base_weights["traffic_intensity"], 0.05),
            "steady_state": st.slider("Steady state", 0.0, 1.0, base_weights["steady_state"], 0.05),
        }

    return AppContext(
        bundle=bundle,
        baseline=baseline,
        scenario=scenario,
        weights=weights,
        manifest=manifest,
        strategy_proxy=load_strategy_proxy(),
        run_path=selected_run,
    )


def _run_provenance(metadata: dict | None, selected_run: str) -> None:
    with st.sidebar.expander("Run provenance", expanded=True):
        if not metadata:
            st.warning("No experiment metadata found.")
            st.caption(selected_run)
            return
        st.write(f"Assignment policy: `{metadata.get('assignment_policy', 'unknown')}`")
        st.write(f"Replications: `{metadata.get('replications', '?')}`")
        st.write(
            f"Horizon: `{metadata.get('warmup_days', '?')}` warm-up, "
            f"`{metadata.get('counted_days', '?')}` counted, "
            f"`{metadata.get('drain_days', '?')}` drain days"
        )
        st.caption(selected_run)


def normalised_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in weights.values()) or 1.0
    return {key: round(max(0.0, value) / total, 3) for key, value in weights.items()}
