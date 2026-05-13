from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import zipfile

import polars as pl
import streamlit as st


APP_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_OUTPUTS_ROOT = APP_ROOT / "data" / "outputs"

REQUIRED_SCENARIO_COLUMNS = {
    "scenario_summary": {"scenario", "group"},
    "scenario_wait_summary": {"scenario", "task_name", "mean_queue_wait_minutes"},
    "scenario_utilisation_summary": {"scenario", "worker_role", "mean_utilisation"},
    "scenario_queue_length_summary": {"scenario"},
}

OPTIONAL_SCENARIO_TABLES = {
    "scenario_replication_results",
    "scenario_steady_state_diagnostics",
}

REQUIRED_SAMPLE_COLUMNS = {
    "events_patient_journey": {"entity_id", "time_in_system_minutes", "total_queue_wait_minutes", "task_path"},
    "events_task": {"entity_id", "task_name", "worker_role", "queued_at", "started_at", "finished_at"},
    "timeseries_daily_kpis": {"day_index", "mean_total_backlog", "mean_queue_wait_minutes"},
    "timeseries_worker_daily_utilisation": {"day_index", "worker_role", "busy_minutes_all", "utilisation_all"},
}


@dataclass(frozen=True)
class DataSource:
    label: str
    outputs_root: Path
    scenario_root: Path
    sample_root: Path
    strategy_proxy_path: Path
    validation_summary: str


def select_data_source() -> DataSource | None:
    with st.sidebar:
        st.markdown("### Scenario Data")
        mode = st.radio(
            "Use bundled data or upload a replacement ZIP",
            options=["Bundled demo data", "Upload ZIP"],
            label_visibility="collapsed",
        )
        if mode == "Upload ZIP":
            uploaded = st.file_uploader("Upload app data ZIP", type=["zip"])
            if uploaded is None:
                st.info("ZIP must include scenario experiment tables. A detailed event-log sample is optional.")
                return _bundled_source()
            try:
                source = _uploaded_source(uploaded.getvalue(), uploaded.name)
            except ValueError as exc:
                st.error(str(exc))
                return None
            st.success(source.validation_summary)
            return source
    return _bundled_source()


def _bundled_source() -> DataSource | None:
    source = _build_source(BUNDLED_OUTPUTS_ROOT, label="Bundled demo data")
    if source is None:
        st.error(
            "No bundled app data found. Upload a ZIP containing scenario outputs or rebuild app/data/outputs."
        )
    return source


@st.cache_resource(show_spinner=False)
def _uploaded_source(upload_bytes: bytes, filename: str) -> DataSource:
    temp_dir = Path(tempfile.mkdtemp(prefix="pharmacy_app_data_"))
    zip_path = temp_dir / filename
    zip_path.write_bytes(upload_bytes)
    with zipfile.ZipFile(zip_path) as archive:
        unsafe = [name for name in archive.namelist() if Path(name).is_absolute() or ".." in Path(name).parts]
        if unsafe:
            raise ValueError("Upload rejected: ZIP contains unsafe paths.")
        archive.extractall(temp_dir)
    root = _normalise_uploaded_root(temp_dir)
    scenario_errors = validate_scenario_root(_scenario_root(root))
    if scenario_errors:
        detail = "; ".join(scenario_errors[:8])
        raise ValueError(f"Upload rejected: required scenario columns are missing. {detail}")
    source = _build_source(root, label=f"Uploaded ZIP: {filename}")
    if source is None:
        raise ValueError(
            "Upload rejected: no valid scenario experiment run found. "
            "Include scenario_summary plus wait, utilisation, and queue-length tables."
        )
    return source


def _normalise_uploaded_root(temp_dir: Path) -> Path:
    if (temp_dir / "outputs").exists():
        return temp_dir / "outputs"
    children = [path for path in temp_dir.iterdir() if path.is_dir()]
    if len(children) == 1 and (children[0] / "outputs").exists():
        return children[0] / "outputs"
    return temp_dir


def _build_source(outputs_root: Path, *, label: str) -> DataSource | None:
    scenario_root = _scenario_root(outputs_root)
    sample_root = outputs_root
    strategy_proxy_path = outputs_root / "scenario_strategy_effort_cost_proxy.csv"
    run_errors = validate_scenario_root(scenario_root)
    if run_errors:
        return None
    sample_errors = validate_sample_root(sample_root)
    sample_note = "Detailed sample logs available." if not sample_errors else "Detailed sample logs not bundled."
    return DataSource(
        label=label,
        outputs_root=outputs_root,
        scenario_root=scenario_root,
        sample_root=sample_root,
        strategy_proxy_path=strategy_proxy_path,
        validation_summary=f"Scenario tables loaded. {sample_note}",
    )


def _scenario_root(outputs_root: Path) -> Path:
    candidate = outputs_root / "scenario_experiments"
    return candidate if candidate.exists() else outputs_root


def validate_scenario_root(root: Path) -> list[str]:
    if not root.exists():
        return [f"Missing scenario root: {root}"]
    run_dirs = _run_dirs(root)
    if not run_dirs:
        return ["No scenario_summary table found."]
    errors = []
    for run_dir in run_dirs:
        errors.extend(_validate_run_dir(run_dir))
    return errors


def validate_sample_root(root: Path) -> list[str]:
    sample_dirs = _sample_dirs(root)
    if not sample_dirs:
        return ["No detailed sample event-log folder found."]
    errors = []
    for sample_dir in sample_dirs[:3]:
        for stem, required in REQUIRED_SAMPLE_COLUMNS.items():
            path = _table_path(sample_dir, stem)
            if not path.exists():
                errors.append(f"{sample_dir.name}: missing {stem}.parquet or {stem}.csv")
                continue
            errors.extend(_validate_columns(path, required))
    return errors


def _validate_run_dir(run_dir: Path) -> list[str]:
    errors = []
    for stem, required in REQUIRED_SCENARIO_COLUMNS.items():
        path = _table_path(run_dir, stem)
        if not path.exists():
            errors.append(f"{run_dir.name}: missing {stem}.parquet or {stem}.csv")
            continue
        errors.extend(_validate_columns(path, required))
    for stem in OPTIONAL_SCENARIO_TABLES:
        path = _table_path(run_dir, stem)
        if path.exists():
            errors.extend(_validate_columns(path, {"scenario"}))
    return errors


def _validate_columns(path: Path, required: set[str]) -> list[str]:
    try:
        columns = set(_read_schema(path))
    except Exception as exc:  # pragma: no cover - defensive upload reporting
        return [f"{path.name}: could not read schema ({exc})"]
    missing = sorted(required - columns)
    return [f"{path.name}: missing columns {', '.join(missing)}"] if missing else []


def _read_schema(path: Path) -> list[str]:
    if path.suffix == ".parquet":
        return pl.scan_parquet(path).collect_schema().names()
    return pl.read_csv(path, n_rows=0).columns


def _run_dirs(root: Path) -> list[Path]:
    return sorted(
        {
            path.parent
            for path in root.rglob("*")
            if path.name in {"scenario_summary.parquet", "scenario_summary.csv"}
        }
    )


def _sample_dirs(root: Path) -> list[Path]:
    return sorted(
        {
            path.parent
            for path in root.rglob("*")
            if path.name in {"events_patient_journey.parquet", "events_patient_journey.csv"}
        }
    )


def _table_path(run_dir: Path, stem: str) -> Path:
    parquet_path = run_dir / f"{stem}.parquet"
    if parquet_path.exists():
        return parquet_path
    return run_dir / f"{stem}.csv"
