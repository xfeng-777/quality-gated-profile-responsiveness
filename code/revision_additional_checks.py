from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def truth(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"expected True/False, got {value!r}")
    return normalized == "true"


def close(value: float, expected: float, tolerance: float = 1e-4) -> bool:
    return abs(value - expected) <= tolerance


def verify_doc_cue_control() -> dict[str, Any]:
    root = DATA / "revision_doc_cue_control"
    initial = read_csv(root / "initial_rater_scores.csv")
    final = read_csv(root / "final_doc_cue_control_decisions.csv")
    metrics = read_csv(root / "final_doc_and_system_sensitivity_metrics.csv")
    gate = json.loads((root / "final_composite_gate_audit.json").read_text(encoding="utf-8"))

    by_id: dict[str, list[dict[str, str]]] = {}
    for row in initial:
        by_id.setdefault(row["rerating_id"], []).append(row)
    agreement = sum(
        len(rows) == 2 and rows[0]["assignment"] == rows[1]["assignment"]
        for rows in by_id.values()
    )
    d1 = {row["rerating_id"]: row["assignment"] for row in initial if row["rater_id"] == "D1"}
    d2 = {row["rerating_id"]: row["assignment"] for row in initial if row["rater_id"] == "D2"}
    final_by_id = {row["rerating_id"]: row["final_assignment"] for row in final}
    disagreements = [rid for rid in by_id if d1[rid] != d2[rid]]
    d3_matches_d1 = sum(final_by_id[rid] == d1[rid] for rid in disagreements)
    d3_matches_d2 = sum(final_by_id[rid] == d2[rid] for rid in disagreements)
    d3_third_choice = sum(
        final_by_id[rid] not in {d1[rid], d2[rid]} for rid in disagreements
    )
    adjudicated = sum(row["decision_source"] == "D3_adjudication" for row in final)

    doc = next(
        row for row in metrics
        if row["analysis"] == "formal_doc_cue_control" and row["scope"] == "all"
    )
    combined = next(
        row for row in metrics
        if row["analysis"] == "formal_phase_a_doc_path_cue_control_sensitivity"
        and row["scope"] == "all"
    )
    checks = {
        "two_initial_ratings_per_doc_unit": len(initial) == 40 and len(by_id) == 20
        and all(len(rows) == 2 for rows in by_id.values()),
        "initial_exact_agreement_9_of_20": agreement == 9,
        "eleven_units_adjudicated": len(final) == 20 and adjudicated == 11,
        "d3_choice_pattern_7_2_2": (d3_matches_d1, d3_matches_d2, d3_third_choice)
        == (7, 2, 2),
        "doc_final_counts": sum(truth(row["full_match"]) for row in final) == 11
        and sum(truth(row["extreme_pair_correct"]) for row in final) == 16
        and sum(truth(row["extreme_reversed"]) for row in final) == 4,
        "doc_metric_regression": close(float(doc["FM"]), 0.55)
        and close(float(doc["POA"]), 0.7667)
        and close(float(doc["DCR"]), 0.80)
        and close(float(doc["ER"]), 0.20)
        and close(float(doc["QG_FM"]), 0.55),
        "combined_metric_regression": close(float(combined["FM"]), 0.77)
        and close(float(combined["POA"]), 0.87)
        and close(float(combined["DCR"]), 0.89)
        and close(float(combined["ER"]), 0.11)
        and close(float(combined["QG_FM"]), 0.76),
        "frozen_composite_gate_unmet": gate["all_conditions_met"] is False
        and gate["criteria"]["every_agent_reverse_le_0_15"] is False
        and gate["criteria"]["historical_ab_kappa_ge_0_60"] is False,
    }
    return {"status": "pass" if all(checks.values()) else "fail", "checks": checks}


def verify_surface_cue_analysis() -> dict[str, Any]:
    root = DATA / "revision_surface_cues"
    features = read_csv(root / "formal_phase_a_surface_features.csv")
    predictions = read_csv(root / "formal_phase_a_surface_cue_prediction.csv")
    analysis = json.loads((root / "formal_phase_a_surface_cue_analysis.json").read_text(encoding="utf-8"))
    by_scope = {row["scope"]: row for row in predictions}
    expected_accuracy = {
        "all": 0.4433,
        "reading": 0.4667,
        "quiz": 0.4500,
        "doc": 0.3167,
        "code": 0.2833,
        "path": 0.9833,
    }
    checks = {
        "formal_output_count": len(features) == 300,
        "scope_coverage": set(by_scope) == set(expected_accuracy),
        "grouped_accuracy_regression": all(
            close(float(by_scope[scope]["surface_model_accuracy"]), value)
            for scope, value in expected_accuracy.items()
        ),
        "task_grouping_retained": all(int(row["task_groups"]) == 20 for row in predictions),
        "permutation_count_documented": analysis["permutation_test"].startswith("2000 "),
        "path_signal_and_doc_code_boundary": float(by_scope["path"]["within_task_permutation_p"]) < 0.01
        and float(by_scope["doc"]["within_task_permutation_p"]) > 0.05
        and float(by_scope["code"]["within_task_permutation_p"]) > 0.05,
    }
    return {"status": "pass" if all(checks.values()) else "fail", "checks": checks}
