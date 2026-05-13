from __future__ import annotations

import math
from pathlib import Path

import polars as pl

from .metrics import BASELINE_SCENARIO


DEFAULT_WEIGHTS = {
    "time_in_system": 0.35,
    "medrec_24h": 0.25,
    "throughput": 0.15,
    "traffic_intensity": 0.10,
    "steady_state": 0.15,
}

STRATEGY_PROXY_FILE = (
    Path(__file__).resolve().parents[2] / "app" / "data" / "outputs" / "scenario_strategy_effort_cost_proxy.csv"
)

GROUP_COST_DEFAULTS = {
    "A": {
        "implementation_score": 3.0,
        "governance_risk": 2.0,
        "category_hint": "Error/rework policy",
    },
    "B": {
        "implementation_score": 7.0,
        "governance_risk": 2.0,
        "category_hint": "Staffing capacity",
    },
    "C": {
        "implementation_score": 5.0,
        "governance_risk": 2.0,
        "category_hint": "Technology/process",
    },
    "D": {
        "implementation_score": 6.0,
        "governance_risk": 4.0,
        "category_hint": "Role flexibility",
    },
    "E": {
        "implementation_score": 0.0,
        "governance_risk": 0.0,
        "category_hint": "Stress test",
    },
    "F": {
        "implementation_score": 4.0,
        "governance_risk": 3.0,
        "category_hint": "Discharge-writing policy",
    },
    "G": {
        "implementation_score": 8.0,
        "governance_risk": 3.0,
        "category_hint": "Combined package",
    },
}


def build_ranking(
    summary: pl.DataFrame,
    *,
    baseline: str = BASELINE_SCENARIO,
    weights: dict[str, float] | None = None,
    strategy_proxy: pl.DataFrame | None = None,
) -> pl.DataFrame:
    if summary.height == 0:
        return pl.DataFrame()
    weights = _normalised_weights(weights or DEFAULT_WEIGHTS)
    base = _row(summary, baseline)
    rows = []
    for row in summary.to_dicts():
        scenario = row.get("scenario")
        group = str(row.get("group") or "")
        time_delta = _to_float(base.get("mean_time_in_system_minutes")) - _to_float(
            row.get("mean_time_in_system_minutes")
        )
        medrec_delta = _to_float(row.get("mean_medrec_within_24h_rate")) - _to_float(
            base.get("mean_medrec_within_24h_rate")
        )
        throughput_delta = _to_float(row.get("mean_throughput")) - _to_float(
            base.get("mean_throughput")
        )
        traffic_delta = _to_float(base.get("mean_traffic_intensity_proxy")) - _to_float(
            row.get("mean_traffic_intensity_proxy")
        )
        steady_score = _steady_state_score(row.get("typical_steady_state_status"))
        base_steady_score = _steady_state_score(
            base.get("typical_steady_state_status")
        )
        steady_delta = steady_score - base_steady_score
        rows.append(
            {
                "scenario": scenario,
                "group": group,
                "mean_time_delta_minutes": -time_delta,
                "medrec_24h_delta_pp": medrec_delta * 100,
                "throughput_delta": throughput_delta,
                "traffic_intensity_delta": -traffic_delta,
                "steady_state_delta": steady_delta,
                "time_improvement": time_delta,
                "medrec_improvement": medrec_delta,
                "throughput_improvement": throughput_delta,
                "traffic_improvement": traffic_delta,
                "steady_state_improvement": steady_delta,
            }
        )
    frame = pl.DataFrame(rows)
    scored = frame.with_columns(
        [
            _normalise_positive(frame, "time_improvement").alias("time_score"),
            _normalise_positive(frame, "medrec_improvement").alias("medrec_score"),
            _normalise_positive(frame, "throughput_improvement").alias("throughput_score"),
            _normalise_positive(frame, "traffic_improvement").alias("traffic_score"),
            _normalise_positive(frame, "steady_state_improvement").alias("steady_state_score"),
        ]
    )
    scored = scored.with_columns(
        (
            pl.col("time_score") * weights["time_in_system"]
            + pl.col("medrec_score") * weights["medrec_24h"]
            + pl.col("throughput_score") * weights["throughput"]
            + pl.col("traffic_score") * weights["traffic_intensity"]
            + pl.col("steady_state_score") * weights["steady_state"]
        ).alias("benefit_score")
    )
    cost_rows = [_cost_assumptions(row["scenario"], row["group"], strategy_proxy) for row in scored.to_dicts()]
    cost_frame = pl.DataFrame(cost_rows)
    scored = scored.join(cost_frame, on=["scenario", "group"], how="left")
    scored = scored.with_columns(
        pl.when(pl.col("implementation_score") > 0)
        .then(pl.col("benefit_score") / pl.col("implementation_score"))
        .otherwise(None)
        .alias("cost_effectiveness_score")
    )
    scored = scored.with_columns(
        pl.struct(["group", "benefit_score", "implementation_score", "governance_risk"])
        .map_elements(_classify, return_dtype=pl.String)
        .alias("category")
    )
    return scored.sort("cost_effectiveness_score", descending=True, nulls_last=True)


def load_strategy_proxy(path: Path | None = None) -> pl.DataFrame | None:
    proxy_path = path or STRATEGY_PROXY_FILE
    if not proxy_path.exists():
        return None
    return pl.read_csv(proxy_path)


def _normalise_positive(frame: pl.DataFrame, column: str) -> pl.Series:
    values = [max(0.0, _to_float(value)) for value in frame[column].to_list()]
    max_value = max(values) if values else 0.0
    if max_value <= 0 or math.isclose(max_value, 0.0):
        return pl.Series([0.0 for _ in values])
    return pl.Series([value / max_value for value in values])


def _normalised_weights(weights: dict[str, float]) -> dict[str, float]:
    merged = {**DEFAULT_WEIGHTS, **weights}
    total = sum(max(0.0, value) for value in merged.values()) or 1.0
    return {key: max(0.0, value) / total for key, value in merged.items()}


def _row(summary: pl.DataFrame, scenario: str) -> dict:
    frame = summary.filter(pl.col("scenario") == scenario)
    if frame.height:
        return frame.to_dicts()[0]
    return summary.to_dicts()[0]


def _steady_state_score(status: object) -> float:
    text = str(status or "").lower()
    if "closest" in text or "steady_state" == text:
        return 1.0
    if "not" in text:
        return 0.0
    return 0.5


def _implementation_score(group: str) -> float:
    return GROUP_COST_DEFAULTS.get(group, {}).get("implementation_score", 5.0)


def _governance_risk(group: str) -> float:
    return GROUP_COST_DEFAULTS.get(group, {}).get("governance_risk", 2.0)


def _cost_assumptions(
    scenario: str,
    group: str,
    strategy_proxy: pl.DataFrame | None,
) -> dict:
    defaults = GROUP_COST_DEFAULTS.get(group, {})
    row = {
        "scenario": scenario,
        "group": group,
        **_component_costs(scenario, group),
        "cost_proxy": "Default group-level proxy",
        "implementation_time_proxy": "Not specified",
        "effort_proxy": defaults.get("category_hint", "Not specified"),
        "stakeholder_use": "Review assumptions before using the ranking.",
        "cost_source": "group default",
    }
    proxy_row = _match_strategy_proxy(scenario, group, strategy_proxy)
    if proxy_row:
        row.update(
            {
                "cost_proxy": proxy_row.get("cost_proxy", row["cost_proxy"]),
                "implementation_time_proxy": proxy_row.get(
                    "implementation_time_proxy",
                    row["implementation_time_proxy"],
                ),
                "effort_proxy": proxy_row.get("effort_proxy", row["effort_proxy"]),
                "stakeholder_use": proxy_row.get("stakeholder_use", row["stakeholder_use"]),
                "cost_source": "strategy proxy file",
            }
        )
        component_costs = _component_costs(scenario, group)
        row.update(component_costs)
        if row["implementation_score"] == _implementation_score(group):
            row["implementation_score"] = _score_cost_proxy(row["cost_proxy"], scenario, group)
        row["governance_risk"] = max(
            float(row["governance_risk"]),
            _score_governance(row["effort_proxy"], group),
        )
    return row


def _component_costs(scenario: str, group: str) -> dict:
    staffing = 0.0
    it_process = 0.0
    role_scope = 0.0
    stress = 0.0
    hours = 0.0
    training_governance = 0.0
    notes: list[str] = []

    if group == "B":
        count = _staff_count(scenario)
        role_weight = _staff_role_weight(scenario)
        staffing = role_weight + count
        training_governance = 1.0 if "senior" not in scenario else 1.5
        notes.append(f"staffing role weight {role_weight:g} + {count} extra per CPU")
    elif group == "C":
        it_process = 4.0 if "automation" not in scenario else 6.0
        training_governance = 1.0
        notes.append("IT/process improvement component")
    elif group == "D":
        role_scope = 3.0
        training_governance = 3.0
        notes.append("role-scope and competency sign-off component")
    elif group == "E":
        stress = 0.0
        hours = 0.0
        notes.append("stress/sensitivity case, not a direct implementation")
    elif group == "F":
        role_scope = 2.0
        training_governance = 2.5
        notes.append("prescribing governance and senior-capacity component")
    elif scenario == "G1_practical_capacity_plus_it":
        staffing = 4.5
        it_process = 3.0
        training_governance = 1.0
        notes.append("technician + junior capacity with IT/process improvement")
    elif scenario == "G2_technician_scope_plus_it":
        role_scope = 3.0
        it_process = 3.0
        training_governance = 3.0
        notes.append("technician scope/training with IT/process improvement")
    elif scenario == "G3_busy_month_resilience_package":
        staffing = 6.5
        it_process = 3.0
        stress = 0.0
        training_governance = 1.5
        notes.append("busy-month stress test plus staffing and IT recovery levers")
    elif scenario == "G4_0900_1700_capacity_recovery_package":
        staffing = 4.5
        it_process = 3.0
        hours = 0.0
        training_governance = 1.0
        notes.append("09:00-17:00 sensitivity plus staffing and IT recovery levers")
    else:
        fallback = _implementation_score(group)
        notes.append("fallback group-level component")
        staffing = fallback

    implementation_score = min(
        staffing + it_process + role_scope + stress + hours + training_governance,
        10.0,
    )
    governance_risk = max(_governance_risk(group), min(role_scope + training_governance, 5.0))
    if group == "E":
        implementation_score = 0.0
        governance_risk = 0.0

    return {
        "implementation_score": implementation_score,
        "governance_risk": governance_risk,
        "staffing_component": staffing,
        "it_process_component": it_process,
        "role_scope_component": role_scope,
        "stress_test_component": stress,
        "hours_sensitivity_component": hours,
        "training_governance_component": training_governance,
        "component_notes": "; ".join(notes),
    }


def _match_strategy_proxy(
    scenario: str,
    group: str,
    strategy_proxy: pl.DataFrame | None,
) -> dict | None:
    if strategy_proxy is None or strategy_proxy.height == 0:
        return None
    family = _family_for_scenario(scenario, group)
    matches = strategy_proxy.filter(pl.col("strategy_family") == family)
    return matches.to_dicts()[0] if matches.height else None


def _family_for_scenario(scenario: str, group: str) -> str:
    if group == "B" or scenario in {"G1_practical_capacity_plus_it", "G3_busy_month_resilience", "G4_standard_hours_recovery"}:
        return "staffing"
    if group == "C":
        return "automation / better IT"
    if group == "D" or scenario == "G2_technician_scope_plus_it":
        return "technician scope / pooling"
    if group == "A":
        return "rework/error reduction"
    if group == "F":
        return "pharmacy discharge writing share"
    if group == "E":
        return "working-hours sensitivity" if "standard_hours" in scenario else "demand surge / holiday resilience"
    if group == "G":
        return "staffing"
    return ""


def _score_cost_proxy(cost_proxy: object, scenario: str, group: str) -> float:
    text = str(cost_proxy or "").lower()
    score = _implementation_score(group)
    if "not a standalone intervention" in text or "stress test" in text:
        return 0.0
    if "high recurring" in text:
        score = 7.0
    elif "medium to high" in text:
        score = 6.0
    elif "medium" in text:
        score = 4.5
    if group == "B":
        score += _staff_count(scenario) - 1
    if group == "G":
        score += 1.0
    return min(score, 10.0)


def _staff_role_weight(scenario: str) -> float:
    if "technician" in scenario:
        return 3.5
    if "junior" in scenario:
        return 4.5
    if "senior" in scenario:
        return 5.5
    return 4.0


def _score_governance(effort_proxy: object, group: str) -> float:
    text = str(effort_proxy or "").lower()
    if "governance" in text or "competency" in text:
        return 4.0
    if group in {"D", "F"}:
        return 3.0
    return _governance_risk(group)


def _staff_count(scenario: str) -> int:
    try:
        return int(scenario.rsplit("_plus_", 1)[1].split("_", 1)[0])
    except (IndexError, ValueError):
        return 1


def _classify(row: dict) -> str:
    group = row["group"]
    benefit = row["benefit_score"]
    cost = row["implementation_score"]
    risk = row["governance_risk"]
    if group == "E":
        return "Stress-test only"
    if risk >= 4 and benefit < 0.35:
        return "Governance-sensitive"
    if risk >= 4:
        return "Governance-sensitive improvement"
    if benefit >= 0.65 and cost <= 6:
        return "Strong candidate"
    if benefit >= 0.35 and cost <= 4:
        return "Cost-effective quick win"
    if benefit >= 0.65 and cost > 6:
        return "High-impact, higher effort"
    if benefit >= 0.35 and cost > 6:
        return "Material improvement, higher effort"
    if benefit >= 0.20:
        return "Material improvement"
    if benefit > 0.05:
        return "Limited improvement"
    return "No clear benefit"


def _to_float(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
