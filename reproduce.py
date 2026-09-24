from __future__ import annotations

import csv
import json
import math
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CODE = ROOT / "code"
DATA = ROOT / "data"
EXPECTED = ROOT / "expected"
GENERATED = ROOT / "generated"
PROTOCOLS = ROOT / "protocols"
sys.path.insert(0, str(CODE))

import cue_control_sensitivity  # noqa: E402
import default_contract_sensitivity  # noqa: E402
import generation_model_comparison as model_comparison  # noqa: E402
import phase_a_decision_sensitivity  # noqa: E402
import revision_additional_checks  # noqa: E402
import statistical_analysis  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def truth(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"expected True/False, got {value!r}")
    return normalized == "true"


def yes(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"yes", "no"}:
        raise ValueError(f"expected yes/no, got {value!r}")
    return normalized == "yes"


def grouped(rows: list[dict[str, Any]]) -> list[tuple[str, str, list[dict[str, Any]]]]:
    result = [("overall", "ALL", list(rows))]
    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_agent[str(row["agent_id"])].append(row)
    result.extend(("agent", agent, by_agent[agent]) for agent in sorted(by_agent))
    return result


def reproduce_formal_phase_a() -> None:
    output = GENERATED / "formal_phase_a"
    output.mkdir(parents=True, exist_ok=True)
    statistical_analysis.run_analysis(
        DATA / "formal_phase_a" / "formal_phase_a_all_agents_blind_triplet_scores.csv",
        DATA / "formal_phase_a" / "formal_phase_a_all_agents_final_triplet_decisions.csv",
        output,
        bootstrap_samples=10_000,
        seed=20260802,
    )
    phase_a_decision_sensitivity.run_analysis(
        DATA / "formal_phase_a" / "formal_phase_a_all_agents_blind_triplet_scores.csv",
        DATA / "formal_phase_a" / "formal_phase_a_all_agents_final_triplet_decisions.csv",
        output,
        bootstrap_samples=10_000,
        seed=20260813,
    )


def reproduce_cue_control() -> None:
    cue_control_sensitivity.main(emit=False)


def reproduce_default_contract() -> None:
    output = GENERATED / "unseen_topics"
    output.mkdir(parents=True, exist_ok=True)
    default_contract_sensitivity.analyze_default_contract_cluster_sensitivity(
        GENERATED / "cue_control" / "default_contract_leakage_controlled_sensitivity.csv",
        output / "deepseek_default_contract_cluster_sensitivity.csv",
        output / "deepseek_default_contract_cluster_sensitivity.json",
        bootstrap_samples=10_000,
        seed=20260803,
        force=True,
    )


def reproduce_model_comparison() -> None:
    cue_rows = read_csv(
        GENERATED / "cue_control" / "cross_model_leakage_controlled_sensitivity.csv"
    )
    by_condition = {
        (row["course_name"], row["topic"], row["agent_id"], row["repeat"], row["model"]): row
        for row in cue_rows
    }
    triplet_rows: list[dict[str, Any]] = []
    condition_keys = sorted({key[:4] for key in by_condition})
    for key in condition_keys:
        deepseek = by_condition[*key, "DeepSeek"]
        qwen = by_condition[*key, "Qwen"]
        triplet_rows.append({
            "course_name": key[0],
            "topic": key[1],
            "agent_id": key[2],
            "repeat": key[3],
            "deepseek_full_match": truth(deepseek["full_match"]),
            "qwen_full_match": truth(qwen["full_match"]),
            "deepseek_extreme_pair_correct": truth(deepseek["extreme_pair_correct"]),
            "qwen_extreme_pair_correct": truth(qwen["extreme_pair_correct"]),
            "deepseek_quality_eligible": truth(deepseek["quality_eligible"]),
            "qwen_quality_eligible": truth(qwen["quality_eligible"]),
            "deepseek_quality_gated_full_match": truth(deepseek["quality_gated_full_match"]),
            "qwen_quality_gated_full_match": truth(qwen["quality_gated_full_match"]),
            "deepseek_quality_gated_extreme_correct": truth(deepseek["quality_gated_extreme_correct"]),
            "qwen_quality_gated_extreme_correct": truth(qwen["quality_gated_extreme_correct"]),
            "deepseek_pairwise_order_accuracy": float(deepseek["pairwise_order_accuracy"]),
            "qwen_pairwise_order_accuracy": float(qwen["pairwise_order_accuracy"]),
        })

    domain_rows: list[dict[str, Any]] = []
    for row in read_csv(DATA / "unseen_topics" / "deepseek_qwen_generation_domain_pairs.csv"):
        domain_rows.append({
            **row,
            "deepseek_factual_pass": truth(row["deepseek_factual_pass"]),
            "qwen_factual_pass": truth(row["qwen_factual_pass"]),
            "deepseek_major_error": truth(row["deepseek_major_error"]),
            "qwen_major_error": truth(row["qwen_major_error"]),
            "deepseek_quality_floor_pass": truth(row["deepseek_quality_floor_pass"]),
            "qwen_quality_floor_pass": truth(row["qwen_quality_floor_pass"]),
        })

    summary: list[dict[str, Any]] = []
    index = 0
    triplet_metrics = {
        "FM": ("deepseek_full_match", "qwen_full_match"),
        "EC": ("deepseek_extreme_pair_correct", "qwen_extreme_pair_correct"),
        "quality_eligible": ("deepseek_quality_eligible", "qwen_quality_eligible"),
        "QG-FM": ("deepseek_quality_gated_full_match", "qwen_quality_gated_full_match"),
        "QG-EC": (
            "deepseek_quality_gated_extreme_correct",
            "qwen_quality_gated_extreme_correct",
        ),
    }
    for group_type, group_key, rows in grouped(triplet_rows):
        for metric, fields in triplet_metrics.items():
            summary.append(model_comparison._binary_summary(
                rows,
                level="triplet",
                group_type=group_type,
                group_key=group_key,
                metric=metric,
                deepseek_field=fields[0],
                qwen_field=fields[1],
                bootstrap_samples=10_000,
                seed=20260803 + index,
            ))
            index += 1
        summary.append(model_comparison._continuous_summary(
            rows,
            level="triplet",
            group_type=group_type,
            group_key=group_key,
            metric="POA",
            deepseek_field="deepseek_pairwise_order_accuracy",
            qwen_field="qwen_pairwise_order_accuracy",
            bootstrap_samples=10_000,
            seed=20260803 + index,
        ))
        index += 1

    domain_metrics = {
        "factual_pass": ("deepseek_factual_pass", "qwen_factual_pass", False),
        "major_error": ("deepseek_major_error", "qwen_major_error", True),
        "quality_floor_pass": (
            "deepseek_quality_floor_pass",
            "qwen_quality_floor_pass",
            False,
        ),
    }
    for group_type, group_key, rows in grouped(domain_rows):
        for metric, fields in domain_metrics.items():
            summary.append(model_comparison._binary_summary(
                rows,
                level="domain_output",
                group_type=group_type,
                group_key=group_key,
                metric=metric,
                deepseek_field=fields[0],
                qwen_field=fields[1],
                bootstrap_samples=10_000,
                seed=20260803 + index,
                lower_is_better=fields[2],
            ))
            index += 1
        if group_key in {"ALL", "code"}:
            applicable = [
                row for row in rows
                if row["deepseek_answer_consistency"] != "na"
                and row["qwen_answer_consistency"] != "na"
            ]
            enriched = [
                {
                    **row,
                    "deepseek_answer_consistency_pass": yes(row["deepseek_answer_consistency"]),
                    "qwen_answer_consistency_pass": yes(row["qwen_answer_consistency"]),
                    "deepseek_structurally_valid_pass": yes(row["deepseek_structurally_valid"]),
                    "qwen_structurally_valid_pass": yes(row["qwen_structurally_valid"]),
                }
                for row in applicable
            ]
            for metric, fields in {
                "answer_consistency": (
                    "deepseek_answer_consistency_pass",
                    "qwen_answer_consistency_pass",
                ),
                "structurally_valid": (
                    "deepseek_structurally_valid_pass",
                    "qwen_structurally_valid_pass",
                ),
            }.items():
                summary.append(model_comparison._binary_summary(
                    enriched,
                    level="domain_output",
                    group_type=group_type,
                    group_key=group_key,
                    metric=metric,
                    deepseek_field=fields[0],
                    qwen_field=fields[1],
                    bootstrap_samples=10_000,
                    seed=20260803 + index,
                ))
                index += 1

    output = GENERATED / "unseen_topics"
    write_csv(output / "deepseek_qwen_generation_comparison_summary.csv", summary)


def compare_csv(expected: Path, generated: Path, tolerance: float = 1e-12) -> dict[str, Any]:
    expected_rows = read_csv(expected)
    generated_rows = read_csv(generated)
    if len(expected_rows) != len(generated_rows):
        return {"status": "fail", "reason": "row_count", "expected": len(expected_rows), "generated": len(generated_rows)}
    differences = []
    for row_index, (left, right) in enumerate(zip(expected_rows, generated_rows), 1):
        if set(left) != set(right):
            return {"status": "fail", "reason": "columns", "row": row_index}
        for field in left:
            left_value, right_value = left[field].strip(), right[field].strip()
            if left_value == right_value:
                continue
            try:
                numeric_equal = math.isclose(
                    float(left_value), float(right_value), rel_tol=tolerance, abs_tol=tolerance
                )
            except ValueError:
                numeric_equal = False
            if not numeric_equal:
                differences.append({
                    "row": row_index,
                    "field": field,
                    "expected": left_value,
                    "generated": right_value,
                })
                if len(differences) >= 10:
                    break
        if len(differences) >= 10:
            break
    return {"status": "pass" if not differences else "fail", "differences": differences}


def verify_e2_e3() -> dict[str, Any]:
    quality = read_csv(DATA / "e2_quality" / "e2_formal_phase_a_quality_by_agent_2026-07-31.csv")
    total_outputs = sum(int(row["total_rows"]) for row in quality)
    quality_passes = sum(int(row["quality_floor_pass_rows"]) for row in quality)
    entry = read_csv(DATA / "e3_entry_channels" / "e3_multimodal_execution_results_2026-07-31.csv")
    entry_passes = sum(yes(row["output_acceptable"]) for row in entry)
    by_modality = Counter(row["modality"] for row in entry if yes(row["output_acceptable"]))
    result = {
        "e2_formal_phase_a": {"outputs": total_outputs, "quality_floor_passes": quality_passes},
        "e3_entry_channels": {
            "cases": len(entry),
            "passes": entry_passes,
            "passes_by_modality": dict(sorted(by_modality.items())),
        },
    }
    expected = {
        "e2_formal_phase_a": {"outputs": 300, "quality_floor_passes": 299},
        "e3_entry_channels": {
            "cases": 15,
            "passes": 14,
            "passes_by_modality": {"image": 5, "text": 5, "voice": 4},
        },
    }
    result["status"] = "pass" if result == expected else "fail"
    result["expected"] = expected
    return result


def verify_e4() -> dict[str, Any]:
    coverage = read_csv(DATA / "e4_run_records" / "e4_condition_coverage.csv")
    batches = read_csv(DATA / "e4_run_records" / "e4_batch_summary.csv")
    keys = [row["e4_condition_key"] for row in coverage]
    main_rows = [row for row in coverage if not row["batch_id"].startswith("unseen_")]
    unseen_rows = [row for row in coverage if row["batch_id"].startswith("unseen_")]
    result = {
        "conditions": len(coverage),
        "unique_condition_keys": len(set(keys)),
        "batches": len(batches),
        "main_evidence_conditions": len(main_rows),
        "unseen_topic_conditions": len(unseen_rows),
        "initial_success_conditions": sum(row["initial_status"] == "ok" for row in coverage),
        "initial_failed_or_missing_conditions": sum(
            row["initial_status"] == "failed_or_missing" for row in coverage
        ),
        "repair_affected_conditions": sum(truth(row["repair_affected"]) for row in coverage),
        "final_covered_conditions": sum(row["final_status"] == "ok" for row in coverage),
        "batch_final_covered_sum": sum(int(row["final_covered_conditions"]) for row in batches),
        "all_batches_complete": all(truth(row["final_coverage_complete"]) for row in batches),
    }
    expected = {
        "conditions": 630,
        "unique_condition_keys": 630,
        "batches": 9,
        "main_evidence_conditions": 420,
        "unseen_topic_conditions": 210,
        "initial_success_conditions": 606,
        "initial_failed_or_missing_conditions": 24,
        "repair_affected_conditions": 30,
        "final_covered_conditions": 630,
        "batch_final_covered_sum": 630,
        "all_batches_complete": True,
    }
    result["status"] = "pass" if result == expected else "fail"
    result["expected"] = expected
    return result


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def verify_protocols() -> dict[str, Any]:
    profile_paths = [
        PROTOCOLS / "profiles" / "p1_beginner.json",
        PROTOCOLS / "profiles" / "p2_intermediate.json",
        PROTOCOLS / "profiles" / "p3_advanced.json",
    ]
    profiles = [json.loads(path.read_text(encoding="utf-8")) for path in profile_paths]
    formal_tasks = read_jsonl(PROTOCOLS / "tasks" / "formal_phase_a_tasks.jsonl")
    unseen_tasks = read_jsonl(PROTOCOLS / "tasks" / "unseen_topic_tasks.jsonl")
    conditions = json.loads((PROTOCOLS / "generation_conditions.json").read_text(encoding="utf-8"))

    checks: dict[str, bool] = {}
    checks["profile_ids"] = [item["profile_id"] for item in profiles] == ["P1", "P2", "P3"]
    varying = {"math", "programming", "statistics", "subject_prior"}
    expected_levels = [1, 3, 5]
    checks["controlled_profile_difference"] = all(
        all(item["profile"]["knowledge_base"][field] == level for field in varying)
        for item, level in zip(profiles, expected_levels)
    )
    reference = profiles[0]["profile"]
    checks["non_target_profile_fields_constant"] = all(
        {
            **item["profile"],
            "knowledge_base": {
                key: value
                for key, value in item["profile"]["knowledge_base"].items()
                if key not in varying
            },
        }
        == {
            **reference,
            "knowledge_base": {
                key: value
                for key, value in reference["knowledge_base"].items()
                if key not in varying
            },
        }
        for item in profiles[1:]
    )

    formal_ids = [row["task_id"] for row in formal_tasks]
    unseen_ids = [row["task_id"] for row in unseen_tasks]
    checks["formal_tasks"] = len(formal_tasks) == 20 and len(set(formal_ids)) == 20
    checks["unseen_tasks"] = len(unseen_tasks) == 10 and len(set(unseen_ids)) == 10
    checks["task_sets_disjoint"] = not (set(formal_ids) & set(unseen_ids))
    checks["five_courses_covered"] = (
        len({row["course_name"] for row in formal_tasks}) == 5
        and len({row["course_name"] for row in unseen_tasks}) == 5
    )

    formal = conditions["formal_phase_a"]
    unseen = conditions["unseen_topics"]
    checks["formal_condition_arithmetic"] = (
        formal["task_count"] * conditions["profiles"]["count"]
        * len(formal["agents"]) * formal["repeat_count"]
        == formal["unique_conditions"] == 300
        and sum(batch["final_conditions"] for batch in formal["execution_batches"]) == 300
    )
    checks["unseen_condition_arithmetic"] = (
        sum(arm["final_conditions"] for arm in unseen["arms"]) == 210
        and unseen["normalized_profiled_outputs"] == 180
        and unseen["normalized_default_contract_outputs"] == 30
    )
    checks["thinking_disabled"] = (
        formal["thinking_mode"] == "disabled"
        and all(arm["thinking_mode"] == "disabled" for arm in unseen["arms"])
    )

    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "formal_task_count": len(formal_tasks),
        "unseen_task_count": len(unseen_tasks),
        "profile_count": len(profiles),
    }


def main() -> int:
    if GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True)
    reproduce_formal_phase_a()
    reproduce_cue_control()
    reproduce_default_contract()
    reproduce_model_comparison()
    checks = {
        "formal_phase_a_metric_uncertainty": compare_csv(
            EXPECTED / "formal_phase_a_metric_uncertainty.csv",
            GENERATED / "formal_phase_a" / "formal_phase_a_metric_uncertainty.csv",
        ),
        "formal_phase_a_rater_reliability": compare_csv(
            EXPECTED / "formal_phase_a_rater_reliability.csv",
            GENERATED / "formal_phase_a" / "formal_phase_a_rater_reliability.csv",
        ),
        "formal_phase_a_decision_sensitivity": compare_csv(
            EXPECTED / "formal_phase_a_decision_sensitivity.csv",
            GENERATED / "formal_phase_a" / "formal_phase_a_decision_sensitivity.csv",
        ),
        "formal_phase_a_final_alignment": compare_csv(
            EXPECTED / "formal_phase_a_final_alignment.csv",
            GENERATED / "formal_phase_a" / "formal_phase_a_final_alignment.csv",
        ),
        "phase_a_interface_aligned_sensitivity": compare_csv(
            EXPECTED / "phase_a_interface_aligned_sensitivity_metrics.csv",
            GENERATED / "cue_control" / "phase_a_interface_aligned_sensitivity_metrics.csv",
        ),
        "default_contract_cue_control": compare_csv(
            EXPECTED / "default_contract_leakage_controlled_sensitivity.csv",
            GENERATED / "cue_control" / "default_contract_leakage_controlled_sensitivity.csv",
        ),
        "cross_model_cue_control": compare_csv(
            EXPECTED / "cross_model_leakage_controlled_sensitivity.csv",
            GENERATED / "cue_control" / "cross_model_leakage_controlled_sensitivity.csv",
        ),
        "default_contract_cluster_sensitivity": compare_csv(
            EXPECTED / "default_contract_leakage_controlled_cluster_sensitivity.csv",
            GENERATED / "unseen_topics" / "deepseek_default_contract_cluster_sensitivity.csv",
        ),
        "generation_model_comparison": compare_csv(
            EXPECTED / "deepseek_qwen_generation_comparison_summary.csv",
            GENERATED / "unseen_topics" / "deepseek_qwen_generation_comparison_summary.csv",
        ),
        "revision_doc_cue_control": revision_additional_checks.verify_doc_cue_control(),
        "revision_surface_cue_analysis": revision_additional_checks.verify_surface_cue_analysis(),
        "e2_e3_summary": verify_e2_e3(),
        "e4_run_coverage": verify_e4(),
        "frozen_protocol_integrity": verify_protocols(),
    }
    overall = "pass" if all(check["status"] == "pass" for check in checks.values()) else "fail"
    report = {"overall_status": overall, "external_api_calls": 0, "checks": checks}
    (GENERATED / "verification_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if overall == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
