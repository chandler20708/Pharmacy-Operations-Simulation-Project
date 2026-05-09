from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from components.deploy_data import DataSource, select_data_source
from core.data_loader import (
    ScenarioOutputBundle,
    discover_scenario_runs,
    load_run,
    load_run_metadata,
    run_display_label,
    scenario_names,
)
from core.scenario_manifest import build_scenario_manifest, scenario_options_with_labels


@dataclass(frozen=True)
class StakeholderContext:
    bundle: ScenarioOutputBundle
    baseline: str
    scenario: str
    run_path: str
    data_source: DataSource


@st.cache_data(show_spinner=False)
def _load_run(run_dir: str):
    return load_run(run_dir)


@st.cache_data(show_spinner=False)
def _load_metadata(run_dir: str):
    return load_run_metadata(run_dir)


def select_context() -> StakeholderContext | None:
    data_source = select_data_source()
    if data_source is None:
        return None

    runs = discover_scenario_runs(data_source.scenario_root)
    if not runs:
        st.error("No scenario experiment outputs found.")
        return None

    run_values = [str(path) for path in runs]
    metadata_by_run = {value: _load_metadata(value) for value in run_values}
    policies = sorted(
        {
            str(metadata.get("assignment_policy"))
            for metadata in metadata_by_run.values()
            if metadata and metadata.get("assignment_policy")
        }
    )
    if not policies:
        st.error("No assignment policy metadata found in scenario outputs.")
        return None

    default_policy = "smart_dynamic" if "smart_dynamic" in policies else policies[0]
    control_a, control_b = st.columns([1, 2])
    with control_a:
        policy = st.selectbox(
            "Test control: assignment policy",
            options=policies,
            index=policies.index(default_policy),
        )

    policy_runs = [
        value
        for value in run_values
        if (metadata_by_run.get(value) or {}).get("assignment_policy") == policy
    ]
    run_path = policy_runs[0]
    bundle = _load_run(run_path)
    baseline, scenario, labels = _scenario_selection(bundle)
    with control_b:
        scenario = st.selectbox(
            "Test control: strategy scenario",
            options=[name for name in scenario_names(bundle.summary) if name != baseline],
            format_func=lambda value: labels.get(value, value),
            index=0,
        )

    with st.expander("Advanced run selection"):
        selected_run = st.selectbox(
            "Output run",
            options=policy_runs,
            format_func=lambda value: run_display_label(Path(value), metadata_by_run.get(value)),
            index=0,
        )
        if selected_run != run_path:
            run_path = selected_run
            bundle = _load_run(run_path)
            baseline, scenario, _labels = _scenario_selection(bundle)

    return StakeholderContext(
        bundle=bundle,
        baseline=baseline,
        scenario=scenario,
        run_path=run_path,
        data_source=data_source,
    )


def _scenario_selection(bundle: ScenarioOutputBundle):
    names = scenario_names(bundle.summary)
    manifest = build_scenario_manifest(bundle.metadata)
    labels = scenario_options_with_labels(names, manifest)
    baseline = "A1_baseline" if "A1_baseline" in names else names[0]
    scenario_options = [name for name in names if name != baseline]
    scenario = scenario_options[0] if scenario_options else baseline
    return baseline, scenario, labels
