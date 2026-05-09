# App Review: Pharmacy Flow Strategy Lab

Date: 2026-05-09

## Scope

This review checks the current Streamlit app against `docs/pharmacy_flow_strategy_lab_mvp_brief.md`, especially:

- section 19: development phases;
- section 21: MVP acceptance criteria;
- section 22: separation of model output, scenario change, decision interpretation, and caveat;
- section 24: suggested first implementation path.

Files reviewed:

- `app/streamlit_app.py`
- `app/pages/1_Strategy_Library.py`
- `app/pages/2_Steady_State_Diagnostics.py`
- `app/pages/3_Cost_Effectiveness.py`
- `app/pages/4_Conceptual_Model.py`
- `app/pages/5_Stakeholder_Export.py`
- `app/components/run_context.py`
- `app/components/dashboard_views.py`
- `app/components/stakeholder_summary.py`
- `app/core/data_loader.py`
- `app/core/metrics.py`
- `app/core/cost_effectiveness.py`
- `app/core/scenario_manifest.py`
- `app/core/sample_outputs.py`
- `app/README.md`
- `tests/test_app_services.py`

## Current Phase Assessment

The app is now best described as:

```text
Phase 1: largely complete
Phase 2: implemented, but needs hardening
Phase 3: not ready yet
```

This is a material improvement from the previous review. The app now has separate pages for strategy library, steady-state diagnostics, cost-effectiveness, conceptual model, and stakeholder export. It also has shared sidebar/run context components.

The app is still **not mature enough to move to Phase 3 custom scenario builder** because Phase 2 ranking and page-level verification are not strong enough yet.

## Checks Run

```bash
./.venv/bin/python -m compileall app
./.venv/bin/python -m pytest tests/test_app_services.py
./.venv/bin/python - <<'PY'
from app.core.data_loader import discover_scenario_runs, load_latest_run, scenario_names
from app.core.metrics import BASELINE_SCENARIO, comparison_snapshot, diagnostics_table
from app.core.cost_effectiveness import build_ranking, load_strategy_proxy
from app.core.scenario_manifest import build_scenario_manifest, assumption_delta_rows, get_scenario_info
from app.components.stakeholder_summary import build_summary
from app.core.sample_outputs import experiment_plots, latest_sample_run, sample_run_plots, sample_patient_journeys

runs = discover_scenario_runs()
bundle = load_latest_run()
names = scenario_names(bundle.summary)
baseline = BASELINE_SCENARIO if BASELINE_SCENARIO in names else names[0]
scenario = next((n for n in names if n != baseline), names[0])
proxy = load_strategy_proxy()
ranking = build_ranking(bundle.summary, baseline=baseline, strategy_proxy=proxy)
snapshot = comparison_snapshot(bundle.summary, bundle.waits, bundle.utilisation, baseline=baseline, scenario=scenario)
manifest = build_scenario_manifest(bundle.metadata)
assumptions = assumption_delta_rows(bundle.metadata, baseline=baseline, scenario=scenario)
info = get_scenario_info(manifest, scenario)
summary = build_summary(bundle.summary, ranking, baseline=baseline, scenario=scenario, scenario_label=info.label, scenario_family=info.family, scenario_description=info.description, scenario_caveat=info.caveat, assumption_rows=assumptions, snapshot=snapshot, metadata=bundle.metadata)
print(len(runs), bundle.summary.shape, len((bundle.metadata or {}).get("scenarios", [])))
print(ranking.shape, snapshot.shape, diagnostics_table(bundle.summary, bundle.queue_lengths, baseline=baseline, scenario=scenario).shape)
print(list(experiment_plots(runs[0]).keys()))
print(list(sample_run_plots(latest_sample_run((bundle.metadata or {}).get("assignment_policy", "smart_dynamic"))).keys()))
print(sample_patient_journeys(latest_sample_run((bundle.metadata or {}).get("assignment_policy", "smart_dynamic"))).shape)
print(summary[:300])
PY
./.venv/bin/streamlit run app/streamlit_app.py --server.port 8565 --server.headless true
```

Observed:

- App modules compile.
- `tests/test_app_services.py` passes: `4 passed`.
- Latest run loads with `summary=(38, 30)`.
- Metadata includes 38 scenario definitions.
- Ranking, comparison snapshot, diagnostics, scenario assumptions, experiment plots, sample plots, sample journeys, and stakeholder summary generation all work at service level.
- Streamlit starts successfully.
- Browser rendering was not fully verified because sandboxed `curl` could not connect to the local Streamlit port after startup.

## Summary Judgment

Phase 1 is close enough to call functionally complete, pending browser/UI verification and page naming cleanup.

Phase 2 exists and is useful, but it remains a proxy ranking layer rather than a mature cost-effectiveness model. Combined strategies, role-specific staffing costs, stress tests, and recovery packages still need sharper treatment.

Do **not** start Phase 3 yet. The next iteration should harden Phase 2 and fix page naming/navigation before adding custom scenario creation.
