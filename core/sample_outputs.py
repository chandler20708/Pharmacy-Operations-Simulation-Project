from __future__ import annotations

from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS_ROOT = PROJECT_ROOT / "app" / "data" / "outputs"


def latest_sample_run(policy: str = "smart_dynamic", *, outputs_root: Path | None = None) -> Path | None:
    root = outputs_root or OUTPUTS_ROOT
    candidates = [
        path.parent
        for path in root.glob(f"scenario_*_{policy}/*/events_patient_journey.parquet")
    ]
    if not candidates:
        candidates = [
            path.parent
            for path in root.glob(f"scenario_*_{policy}/*/events_patient_journey.csv")
        ]
    if not candidates:
        candidates = [
            path.parent for path in root.glob("scenario_*/*/events_patient_journey.parquet")
        ]
    if not candidates:
        candidates = [path.parent for path in root.glob("scenario_*/*/events_patient_journey.csv")]
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[0] if candidates else None


def _table_path(run_dir: Path, stem: str) -> Path:
    parquet_path = run_dir / f"{stem}.parquet"
    if parquet_path.exists():
        return parquet_path
    return run_dir / f"{stem}.csv"


def _read_table(path: Path) -> pl.DataFrame:
    if path.suffix == ".parquet":
        return pl.read_parquet(path)
    return pl.read_csv(path)


def sample_run_plots(run_dir: Path | None) -> dict[str, Path]:
    if run_dir is None:
        return {}
    names = {
        "Patient journey sample": "plot_patient_journeys.png",
        "KPI time series": "plot_kpi_timeseries.png",
        "Steady-state diagnostics": "plot_steady_state_diagnostics.png",
        "Weekly people in system": "plot_weekly_people_in_system.png",
        "System animation": "animation_system_run.gif",
    }
    return {label: run_dir / filename for label, filename in names.items() if (run_dir / filename).exists()}


def experiment_plots(run_dir: str | Path) -> dict[str, Path]:
    run_path = Path(run_dir)
    names = {
        "Scenario scorecard": "plot_scenario_scorecard.png",
        "Delta vs baseline": "plot_delta_vs_baseline.png",
        "Error mechanism impact": "plot_error_mechanism_impact.png",
        "Steady-state distribution check": "plot_steady_state_distribution_check.png",
    }
    return {label: run_path / filename for label, filename in names.items() if (run_path / filename).exists()}


def sample_patient_journeys(run_dir: Path | None, limit: int = 10) -> pl.DataFrame:
    if run_dir is None:
        return pl.DataFrame()
    path = _table_path(run_dir, "events_patient_journey")
    if not path.exists():
        return pl.DataFrame()
    frame = _read_table(path)
    counted = frame.filter(pl.col("counted") == True)
    if counted.height == 0:
        counted = frame
    columns = [
        "entity_id",
        "section_name",
        "ward_name",
        "time_in_system_minutes",
        "total_queue_wait_minutes",
        "total_service_minutes",
        "completed_task_count",
        "task_path",
    ]
    return counted.select([column for column in columns if column in counted.columns]).head(limit)


def sample_task_events(run_dir: Path | None, entity_id: int | None = None) -> pl.DataFrame:
    if run_dir is None:
        return pl.DataFrame()
    path = _table_path(run_dir, "events_task")
    if not path.exists():
        return pl.DataFrame()
    frame = _read_table(path)
    if entity_id is None:
        journeys = sample_patient_journeys(run_dir, limit=1)
        if journeys.height == 0:
            return pl.DataFrame()
        entity_id = int(journeys["entity_id"][0])
    columns = [
        "entity_id",
        "task_name",
        "worker_role",
        "queued_at",
        "started_at",
        "finished_at",
        "queue_wait_minutes",
        "service_minutes",
    ]
    return (
        frame.filter(pl.col("entity_id") == entity_id)
        .select([column for column in columns if column in frame.columns])
        .sort("queued_at")
    )


def daily_kpis(run_dir: Path | None) -> pl.DataFrame:
    if run_dir is None:
        return pl.DataFrame()
    path = _table_path(run_dir, "timeseries_daily_kpis")
    if not path.exists():
        return pl.DataFrame()
    return _read_table(path)


def task_events_window(
    run_dir: Path | None,
    *,
    start_day: int,
    end_day: int,
    limit: int = 28,
) -> pl.DataFrame:
    if run_dir is None:
        return pl.DataFrame()
    path = _table_path(run_dir, "events_task")
    if not path.exists():
        return pl.DataFrame()
    start_minute = start_day * 1440
    end_minute = (end_day + 1) * 1440
    frame = _read_table(path)
    filtered = frame.filter(
        (pl.col("started_at") >= start_minute)
        & (pl.col("started_at") < end_minute)
        & (pl.col("completed_within_horizon") == True)
    )
    if filtered.height == 0:
        return filtered
    columns = [
        "entity_id",
        "section_name",
        "task_name",
        "worker_name",
        "worker_role",
        "queued_at",
        "started_at",
        "finished_at",
        "queue_wait_minutes",
        "service_minutes",
    ]
    return (
        filtered.select([column for column in columns if column in filtered.columns])
        .sort("queue_wait_minutes", descending=True)
        .head(limit)
        .sort("started_at")
    )


def window_summary(run_dir: Path | None, *, start_day: int, end_day: int) -> dict[str, float]:
    frame = daily_kpis(run_dir)
    if frame.height == 0:
        return {}
    window = frame.filter(
        (pl.col("day_index") >= start_day) & (pl.col("day_index") <= end_day)
    )
    if window.height == 0:
        return {}
    return {
        "arrivals": float(window["arrivals_all"].sum()),
        "completions": float(window["completions_all"].sum()),
        "net_flow": float(window["net_flow_all"].sum()),
        "mean_backlog": float(window["mean_total_backlog"].mean()),
        "mean_queue_wait": float(window["mean_queue_wait_minutes"].mean()),
        "mean_time_in_system": float(window["mean_time_in_system_minutes"].mean()),
    }


def role_activity_window(
    run_dir: Path | None,
    *,
    start_day: int,
    end_day: int,
) -> pl.DataFrame:
    if run_dir is None:
        return pl.DataFrame()
    path = _table_path(run_dir, "timeseries_worker_daily_utilisation")
    if not path.exists():
        return pl.DataFrame()
    frame = _read_table(path)
    window = frame.filter(
        (pl.col("day_index") >= start_day) & (pl.col("day_index") <= end_day)
    )
    if window.height == 0:
        return pl.DataFrame()
    return (
        window.group_by("worker_role")
        .agg(
            [
                pl.col("busy_minutes_all").sum().alias("busy_minutes"),
                pl.col("available_minutes_all").sum().alias("available_minutes"),
                pl.col("utilisation_all").mean().alias("mean_utilisation"),
            ]
        )
        .sort("busy_minutes", descending=True)
    )
