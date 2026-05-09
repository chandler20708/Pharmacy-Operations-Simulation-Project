from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import polars as pl


REQUIRED_SUMMARY = "scenario_summary.parquet"
OPTIONAL_FILES = {
    "replications": "scenario_replication_results.parquet",
    "waits": "scenario_wait_summary.parquet",
    "utilisation": "scenario_utilisation_summary.parquet",
    "steady_state": "scenario_steady_state_diagnostics.parquet",
    "queue_lengths": "scenario_queue_length_summary.parquet",
}
CSV_FALLBACK_SUMMARY = "scenario_summary.csv"
CSV_FALLBACK_FILES = {
    key: filename.replace(".parquet", ".csv") for key, filename in OPTIONAL_FILES.items()
}


@dataclass(frozen=True)
class ScenarioOutputBundle:
    run_dir: Path
    summary: pl.DataFrame
    replications: pl.DataFrame | None = None
    waits: pl.DataFrame | None = None
    utilisation: pl.DataFrame | None = None
    steady_state: pl.DataFrame | None = None
    queue_lengths: pl.DataFrame | None = None
    metadata: dict | None = None


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def outputs_root() -> Path:
    bundled = project_root() / "app" / "data" / "outputs" / "scenario_experiments"
    return bundled if bundled.exists() else project_root() / "app" / "data" / "outputs"


def discover_scenario_runs(root: Path | None = None) -> list[Path]:
    search_root = root or outputs_root()
    if not search_root.exists():
        return []
    parquet_runs = [path.parent for path in search_root.rglob(REQUIRED_SUMMARY)]
    csv_only_runs = [
        path.parent
        for path in search_root.rglob(CSV_FALLBACK_SUMMARY)
        if not (path.parent / REQUIRED_SUMMARY).exists()
    ]
    runs = parquet_runs + csv_only_runs
    return sorted(runs, key=lambda path: path.stat().st_mtime, reverse=True)


def load_latest_run(root: Path | None = None) -> ScenarioOutputBundle:
    runs = discover_scenario_runs(root)
    if not runs:
        raise FileNotFoundError(
            f"No {REQUIRED_SUMMARY} files found under {root or outputs_root()}."
        )
    return load_run(runs[0])


def load_run(run_dir: str | Path) -> ScenarioOutputBundle:
    run_path = Path(run_dir)
    summary_path = _resolve_table_path(run_path, REQUIRED_SUMMARY, CSV_FALLBACK_SUMMARY)
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing required summary file: {summary_path}")

    frames: dict[str, pl.DataFrame | None] = {}
    for key, filename in OPTIONAL_FILES.items():
        path = _resolve_table_path(run_path, filename, CSV_FALLBACK_FILES[key])
        frames[key] = _read_table(path) if path.exists() else None

    metadata = _load_metadata(run_path)
    return ScenarioOutputBundle(
        run_dir=run_path,
        summary=_read_table(summary_path),
        replications=frames["replications"],
        waits=frames["waits"],
        utilisation=frames["utilisation"],
        steady_state=frames["steady_state"],
        queue_lengths=frames["queue_lengths"],
        metadata=metadata,
    )


def load_run_metadata(run_dir: str | Path) -> dict | None:
    return _load_metadata(Path(run_dir))


def _load_metadata(run_path: Path) -> dict | None:
    metadata_path = run_path / "experiment_metadata.json"
    if not metadata_path.exists():
        return None
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _resolve_table_path(run_path: Path, parquet_name: str, csv_name: str) -> Path:
    parquet_path = run_path / parquet_name
    if parquet_path.exists():
        return parquet_path
    return run_path / csv_name


def _read_table(path: Path) -> pl.DataFrame:
    if path.suffix == ".parquet":
        return pl.read_parquet(path)
    return pl.read_csv(path)


def scenario_names(summary: pl.DataFrame) -> list[str]:
    if "scenario" not in summary.columns:
        return []
    return summary.select("scenario").unique().sort("scenario")["scenario"].to_list()


def run_display_label(run_dir: Path, metadata: dict | None) -> str:
    if metadata:
        policy = metadata.get("assignment_policy", "unknown policy")
        replications = metadata.get("replications", "?")
        created_at = metadata.get("created_at", run_dir.name)
        return f"{policy} | {replications} reps | {created_at}"
    return run_dir.name
