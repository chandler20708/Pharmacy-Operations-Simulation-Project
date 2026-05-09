from __future__ import annotations

from pathlib import Path

import polars as pl


APP_TABLES = [
    "scenario_summary",
    "scenario_replication_results",
    "scenario_wait_summary",
    "scenario_waits_by_stage",
    "scenario_utilisation_summary",
    "scenario_utilisation_by_role",
    "scenario_steady_state_diagnostics",
    "scenario_queue_length_summary",
    "scenario_queue_lengths",
    "scenario_raw_patient_validation",
    "scenario_discrepancy_validation_summary",
    "scenario_discrepancy_validation_by_replication",
]


def materialize_run_parquet(run_dir: str | Path) -> list[Path]:
    """Create Parquet copies for app-readable scenario outputs."""
    run_path = Path(run_dir)
    written: list[Path] = []
    for stem in APP_TABLES:
        csv_path = run_path / f"{stem}.csv"
        parquet_path = run_path / f"{stem}.parquet"
        if csv_path.exists() and not parquet_path.exists():
            pl.read_csv(csv_path).write_parquet(parquet_path)
            written.append(parquet_path)
    return written
