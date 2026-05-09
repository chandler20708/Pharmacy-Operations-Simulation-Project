# Pharmacy Flow Strategy Lab

Streamlit MVP for comparing NHS pharmacy DES scenario outputs and ranking strategy options by conditional benefit versus implementation effort.

The app is a decision-support dashboard, not a generic simulation editor and not a financial ROI model. It separates model output, scenario assumptions, decision interpretation, and implementation caveats.

## Run The App

From `des_model`:

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app/Executive_Overview.py
```

## Generate Outputs

For the main 30-replication scenario evidence:

```bash
make one-year-30
```

Future runs write Parquet and CSV. Older CSV-only runs can be materialized:

```bash
.venv/bin/python - <<'PY'
from app.core.parquet_materializer import materialize_run_parquet
materialize_run_parquet("outputs/scenario_experiments/<run-folder>")
PY
```

## Output Discovery

The deployed app is self-contained. By default it searches `app/data/outputs/scenario_experiments/` for scenario output folders and sorts them by modification time. It prefers Parquet files and falls back to CSV only when Parquet is missing.

The sidebar also supports an uploaded replacement ZIP. The ZIP can contain either:

- `outputs/scenario_experiments/<run-folder>/...`, or
- `scenario_experiments/<run-folder>/...`, or
- one or more run folders directly containing `scenario_summary.parquet` or `scenario_summary.csv`.

The upload is rejected unless the scenario tables have the columns needed by the app.

The app reads Parquet scenario outputs first:

- `scenario_summary.parquet`
- `scenario_replication_results.parquet`
- `scenario_wait_summary.parquet`
- `scenario_utilisation_summary.parquet`
- `scenario_steady_state_diagnostics.parquet`
- `scenario_queue_length_summary.parquet`

CSV files are retained only as a fallback for older experiment folders.

The app also reads `experiment_metadata.json` when present to show assignment policy, replication count, warm-up/counted/drain days, seed, and scenario selection.

For the diagnostic animation, bundled or uploaded data can also include detailed sample logs under a folder such as `outputs/scenario_baseline_smart_dynamic/<run-folder>/` with:

- `events_patient_journey.parquet`
- `events_task.parquet`
- `timeseries_daily_kpis.parquet`
- `timeseries_worker_daily_utilisation.parquet`

CSV versions are accepted as fallbacks. If detailed logs are not present, the executive overview still works but the diagnostic animation page will report that no detailed event-log sample is available.

## Current Stakeholder View

The app is intentionally a two-page stakeholder view. It avoids exposing the full analyst cockpit by default.

The visible workflow is:

1. Select assignment policy: `priority`, `dynamic`, `smart_dynamic`, or `random` when those runs exist.
2. Select a strategy scenario.
3. Use `Executive Overview` for the decision line, key metrics, patient-time comparison, and one sampled patient journey.
4. Use `Diagnostic Animation` to choose a KPI spike and inspect patient/staff interactions in that simulated time window.
5. Open analyst expanders only when assumption deltas, diagnostics, or raw traces are needed.

This is a deliberate simplification from the earlier analyst-heavy multipage version. Stakeholders see the process and patient experience first; analysts can still inspect detailed tables in expanders.

## Cost-Effectiveness Caveat

Cost-effectiveness is proxy-based unless real cost data are supplied later. The app uses `app/data/outputs/scenario_strategy_effort_cost_proxy.csv` where available and falls back to group defaults otherwise. Uploaded ZIPs can include `scenario_strategy_effort_cost_proxy.csv` at the upload output root. Rankings are conditional on selected KPI weights and implementation assumptions.

## Tests

From `des_model`:

```bash
.venv/bin/python -m py_compile app/Executive_Overview.py app/pages/1_Diagnostic_Animation.py app/core/*.py app/components/*.py
.venv/bin/python -m pytest tests/test_app_services.py
```

## Known Limitations

- Custom scenario building and run-on-demand simulation are still later phases.
- Scenario assumption deltas depend on metadata exported with the experiment.
- Monday-opening backlog is not shown unless it is added to scenario experiment summaries.
- The app may load stale smoke outputs if those are the newest modified folders; check the run provenance panel before using results in a report.
