from __future__ import annotations

from dataclasses import dataclass


GROUP_LABELS = {
    "A": "Error and rework",
    "B": "Staffing capacity",
    "C": "Technology and process efficiency",
    "D": "Role flexibility and training",
    "E": "Demand and working-hours sensitivity",
    "F": "Discharge-writing policy",
    "G": "Combined package",
}


@dataclass(frozen=True)
class ScenarioInfo:
    scenario: str
    label: str
    family: str
    description: str
    caveat: str


def build_scenario_manifest(metadata: dict | None) -> dict[str, ScenarioInfo]:
    manifest: dict[str, ScenarioInfo] = {}
    for item in (metadata or {}).get("scenarios", []):
        scenario = item.get("name", "")
        group = item.get("group", "")
        description = item.get("description", "")
        manifest[scenario] = ScenarioInfo(
            scenario=scenario,
            label=friendly_scenario_label(scenario, description),
            family=GROUP_LABELS.get(group, group or "Unknown"),
            description=description or "No scenario description was exported with this run.",
            caveat=_caveat_for_group(group),
        )
    return manifest


def get_scenario_info(
    manifest: dict[str, ScenarioInfo],
    scenario: str,
    group: str | None = None,
) -> ScenarioInfo:
    if scenario in manifest:
        return manifest[scenario]
    return ScenarioInfo(
        scenario=scenario,
        label=friendly_scenario_label(scenario, ""),
        family=GROUP_LABELS.get(group or "", group or "Unknown"),
        description="No scenario metadata found; using the model scenario ID.",
        caveat="Check the scenario definition before treating this as decision evidence.",
    )


def friendly_scenario_label(scenario: str, description: str = "") -> str:
    if scenario == "A1_baseline":
        return "Current baseline"
    if scenario.startswith("B_"):
        parts = scenario.replace("_per_cpu", "").split("_plus_")
        if len(parts) == 2:
            role = parts[0].replace("B_", "").replace("_", " ")
            return f"Add {parts[1]} {role}{'' if parts[1] == '1' else 's'} per CPU"
    if scenario.startswith("C1_mean_reduction_"):
        return f"Reduce core task mean time by {scenario.rsplit('_', 1)[-1]}%"
    if scenario.startswith("C2_variance_reduction_"):
        return f"Reduce core task variation by {scenario.rsplit('_', 1)[-1]}%"
    if scenario.startswith("C3_mean_variance_reduction_"):
        return f"Reduce core task mean and variation by {scenario.rsplit('_', 1)[-1]}%"
    if scenario == "C4_automation_halves_mean_sd":
        return "Automation halves core task mean and variation"
    if description:
        return description.split(";")[0].split(".")[0][:90]
    return scenario.replace("_", " ").strip().capitalize()


def scenario_options_with_labels(
    scenarios: list[str],
    manifest: dict[str, ScenarioInfo],
) -> dict[str, str]:
    return {
        scenario: f"{get_scenario_info(manifest, scenario).label} ({scenario})"
        for scenario in scenarios
    }


def scenario_classification(scenario: str, group: str | None = None) -> str:
    if scenario == "A1_baseline":
        return "Baseline"
    if group == "A":
        return "Process improvement hypothesis"
    if group == "B":
        return "Intervention"
    if group == "C":
        return "Process improvement hypothesis"
    if group == "D":
        return "Governance-sensitive role change"
    if group == "E":
        if "busy" in scenario or "weekend" in scenario or "time_varying" in scenario:
            return "Stress test"
        return "Sensitivity test"
    if group == "F":
        return "Governance-sensitive role change"
    if group == "G":
        if "recovery" in scenario:
            return "Recovery package"
        return "Combined package"
    return "Unclassified"


def assumption_delta_rows(
    metadata: dict | None,
    *,
    baseline: str,
    scenario: str,
) -> list[dict[str, str]]:
    scenarios = {item.get("name"): item for item in (metadata or {}).get("scenarios", [])}
    base = scenarios.get(baseline, {})
    selected = scenarios.get(scenario, {})
    if not selected:
        return [
            {
                "field": "Scenario definition",
                "baseline": baseline,
                "scenario": scenario,
                "note": "No exported scenario setup found in metadata.",
            }
        ]

    rows = [
        _compare("Assignment rule", base, selected, ("settings", "assignment_policy")),
        _compare("Weekday close hour", base, selected, ("settings", "close_hour")),
        _compare("Saturday availability", base, selected, ("settings", "saturday_availability_multiplier")),
        _compare("Sunday availability", base, selected, ("settings", "sunday_availability_multiplier")),
        _compare("Low-risk exit probability", base, selected, ("pathway_parameters", "low_risk_exit_probability")),
        _compare("Upstream discrepancy probability", base, selected, ("pathway_parameters", "discrepancy_probability")),
        _compare("Pharmacy-written discharge share", base, selected, ("pathway_parameters", "pharmacist_writes_discharge_probability")),
        _compare("Medic error probability", base, selected, ("pathway_parameters", "medic_prescription_error_probability")),
    ]
    rows.extend(_worker_delta_rows(base, selected))
    task_notes = _task_change_notes(base, selected)
    if task_notes:
        rows.append(
            {
                "field": "Task/service assumptions",
                "baseline": "baseline task setup",
                "scenario": "changed task setup",
                "note": "; ".join(task_notes[:4]),
            }
        )
    return rows


def _compare(label: str, base: dict, selected: dict, path: tuple[str, str]) -> dict[str, str]:
    base_value = _nested(base, path)
    scenario_value = _nested(selected, path)
    return {
        "field": label,
        "baseline": _display(base_value),
        "scenario": _display(scenario_value),
        "note": "unchanged" if base_value == scenario_value else "changed",
    }


def _nested(item: dict, path: tuple[str, str]):
    current = item
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _worker_delta_rows(base: dict, selected: dict) -> list[dict[str, str]]:
    base_counts = _worker_counts(base)
    selected_counts = _worker_counts(selected)
    rows = []
    for key in sorted(set(base_counts) | set(selected_counts)):
        base_value = base_counts.get(key, 0)
        selected_value = selected_counts.get(key, 0)
        if base_value != selected_value:
            rows.append(
                {
                    "field": f"Staffing: {key}",
                    "baseline": str(base_value),
                    "scenario": str(selected_value),
                    "note": f"{selected_value - base_value:+d} workers",
                }
            )
    if not rows:
        rows.append(
            {
                "field": "Staffing",
                "baseline": "baseline",
                "scenario": "baseline",
                "note": "unchanged",
            }
        )
    return rows


def _worker_counts(item: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for worker in item.get("workers", []):
        key = f"{worker.get('section_name', 'unknown')} {worker.get('role', 'unknown')}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _task_change_notes(base: dict, selected: dict) -> list[str]:
    base_tasks = {task.get("queue_key"): task for task in base.get("tasks", [])}
    notes = []
    for task in selected.get("tasks", []):
        base_task = base_tasks.get(task.get("queue_key"))
        if not base_task:
            continue
        changed = []
        for field in ("mean_minutes", "sd_minutes", "allowed_roles"):
            if base_task.get(field) != task.get(field):
                changed.append(field)
        if changed:
            notes.append(f"{task.get('name', task.get('queue_key'))}: {', '.join(changed)}")
    return notes


def _display(value) -> str:
    if value is None:
        return "not exported"
    if isinstance(value, float):
        return f"{value:.3g}"
    return str(value)


def _caveat_for_group(group: str) -> str:
    if group == "B":
        return "Assumes extra staff are recruitable, onboarded, and available at the modelled level."
    if group == "C":
        return "Represents process or technology improvement, not a priced IT business case."
    if group == "D":
        return "Requires governance, competency sign-off, and supervision rules."
    if group == "E":
        return "This is mainly a stress test or sensitivity case, not a standalone intervention."
    if group == "F":
        return "May shift workload onto senior pharmacist capacity and prescribing governance."
    if group == "G":
        return "Combines multiple assumptions, so attribution to one lever is limited."
    if group == "A":
        return "Depends on upstream clinical behaviour and error/rework reduction being achievable."
    return "Review operational feasibility before treating this as a recommendation."
