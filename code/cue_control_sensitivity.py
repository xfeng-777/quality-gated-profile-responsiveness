#!/usr/bin/env python3
"""Re-estimate Phase A after replacing Path with interface-aligned reratings.

The historical Phase A files are read-only inputs. Outputs are written to the
leakage-controlled rerating package and are explicitly labelled post hoc.
"""

from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "generated" / "cue_control"
FORMAL = DATA / "formal_phase_a"
UNSEEN = DATA / "unseen_topics"

OLD_FINAL = FORMAL / "formal_phase_a_all_agents_final_triplet_decisions.csv"
OLD_RAW = FORMAL / "formal_phase_a_all_agents_blind_triplet_scores.csv"
NEW_FINAL = DATA / "cue_control" / "final_triplet_decisions.csv"
NEW_SCORES = DATA / "cue_control" / "triplet_rating_scores.csv"
NEW_PAIRWISE = DATA / "cue_control" / "final_pairwise_decisions.csv"
SEED = 20260802
BOOTSTRAP_REPLICATES = 10_000


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "yes", "1"}


def wilson(successes: int, total: int) -> tuple[float, float]:
    z = 1.959963984540054
    estimate = successes / total
    denominator = 1 + z * z / total
    center = (estimate + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(
        estimate * (1 - estimate) / total + z * z / (4 * total * total)
    ) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def categorical_kappa(left: list[str], right: list[str]) -> float | None:
    if not left or len(left) != len(right):
        return None
    n = len(left)
    observed = sum(a == b for a, b in zip(left, right, strict=True)) / n
    left_counts = Counter(left)
    right_counts = Counter(right)
    expected = sum(
        left_counts[label] / n * right_counts[label] / n
        for label in set(left_counts) | set(right_counts)
    )
    return None if expected == 1 else (observed - expected) / (1 - expected)


def assignment(row: dict[str, str], prefix: str = "assigned") -> str:
    if prefix == "assigned":
        values = (
            row["assigned_p1_candidate"],
            row["assigned_p2_candidate"],
            row["assigned_p3_candidate"],
        )
    else:
        values = (
            row["beginner_candidate"],
            row["intermediate_candidate"],
            row["advanced_candidate"],
        )
    return ">".join(value.strip().upper() for value in values)


def build_hybrid_final() -> list[dict[str, Any]]:
    old_rows = read_csv(OLD_FINAL)
    new_path = {
        row["old_triplet_id"]: row
        for row in read_csv(NEW_FINAL)
        if row["batch_id"] == "formal_phase_a_path"
    }
    assert len(old_rows) == 100
    assert len(new_path) == 20

    combined = []
    replaced = set()
    for row in old_rows:
        item: dict[str, Any] = dict(row)
        item["analysis_source"] = "historical_phase_a"
        if row["agent_id"] == "path":
            new = new_path[row["triplet_id"]]
            replaced.add(row["triplet_id"])
            item.update({
                "decision_source": "posthoc_interface_aligned_final",
                "decision_maker": "R1/R2 with R3 adjudication if triggered",
                "decided_at": "2026-08-13",
                "assigned_p1_candidate": "",
                "assigned_p2_candidate": "",
                "assigned_p3_candidate": "",
                "true_p1_candidate": "",
                "true_p2_candidate": "",
                "true_p3_candidate": "",
                "exact_profile_matches": new["exact_profile_matches"],
                "full_match": new["full_match"],
                "pairwise_correct": new["pairwise_correct"],
                "pairwise_total": "3",
                "pairwise_order_accuracy": new["pairwise_order_accuracy"],
                "extreme_pair_correct": new["extreme_pair_correct"],
                "extreme_reversed": new["extreme_reversed"],
                "confidence": new["confidence"],
                "indistinguishable": new["indistinguishable"],
                "quality_gated_full_match": str(
                    as_bool(new["full_match"]) and as_bool(row["quality_eligible"])
                ),
                "quality_gated_extreme_correct": str(
                    as_bool(new["extreme_pair_correct"])
                    and as_bool(row["quality_eligible"])
                ),
                "analysis_source": "posthoc_interface_aligned_path",
            })
        combined.append(item)
    assert replaced == set(new_path)
    return combined


def metrics(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    n = len(rows)
    return {
        "triplets": n,
        "fm_n": sum(as_bool(row["full_match"]) for row in rows),
        "fm": sum(as_bool(row["full_match"]) for row in rows) / n,
        "poa_n": sum(int(row["pairwise_correct"]) for row in rows),
        "poa_d": 3 * n,
        "poa": sum(int(row["pairwise_correct"]) for row in rows) / (3 * n),
        "ec_n": sum(as_bool(row["extreme_pair_correct"]) for row in rows),
        "ec": sum(as_bool(row["extreme_pair_correct"]) for row in rows) / n,
        "er_n": sum(as_bool(row["extreme_reversed"]) for row in rows),
        "er": sum(as_bool(row["extreme_reversed"]) for row in rows) / n,
        "qg_fm_n": sum(as_bool(row["quality_gated_full_match"]) for row in rows),
        "qg_fm": sum(as_bool(row["quality_gated_full_match"]) for row in rows) / n,
    }


def bootstrap_interval(
    rows: list[dict[str, Any]],
    key: Callable[[dict[str, Any]], str],
    statistic: Callable[[list[dict[str, Any]]], float],
    rng: random.Random,
) -> tuple[float, float]:
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        clusters[key(row)].append(row)
    labels = sorted(clusters)
    estimates = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sampled: list[dict[str, Any]] = []
        for _ in labels:
            sampled.extend(clusters[rng.choice(labels)])
        estimates.append(statistic(sampled))
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def metric_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = [("overall", "all", rows)]
    for agent in ("reading", "quiz", "doc", "code", "path"):
        groups.append(("agent", agent, [row for row in rows if row["agent_id"] == agent]))

    output = []
    for group_type, group, selected in groups:
        values = metrics(selected)
        task_key = lambda row: f'{row["course_name"]}|{row["topic"]}'
        rng = random.Random(f"{SEED}:{group_type}:{group}")
        cluster_intervals = {}
        for metric_name in ("fm", "poa", "ec", "er", "qg_fm"):
            low, high = bootstrap_interval(
                selected,
                task_key,
                lambda sample, name=metric_name: float(metrics(sample)[name]),
                rng,
            )
            cluster_intervals[metric_name] = (low, high)

        for metric_name, numerator_name, denominator in (
            ("fm", "fm_n", len(selected)),
            ("poa", "poa_n", 3 * len(selected)),
            ("ec", "ec_n", len(selected)),
            ("er", "er_n", len(selected)),
            ("qg_fm", "qg_fm_n", len(selected)),
        ):
            if metric_name == "poa":
                rng_triplet = random.Random(f"{SEED}:triplet:{group_type}:{group}")
                conventional = bootstrap_interval(
                    selected,
                    lambda row: row["triplet_id"],
                    lambda sample: float(metrics(sample)["poa"]),
                    rng_triplet,
                )
                method = "triplet cluster bootstrap"
            else:
                conventional = wilson(int(values[numerator_name]), denominator)
                method = "Wilson score"
            task_interval = cluster_intervals[metric_name]
            output.append({
                "group_type": group_type,
                "group": group,
                "triplets": len(selected),
                "metric": metric_name.upper().replace("_", "-"),
                "numerator": values[numerator_name],
                "denominator": denominator,
                "estimate": round(float(values[metric_name]), 4),
                "conventional_ci_method": method,
                "conventional_ci_95_low": round(conventional[0], 4),
                "conventional_ci_95_high": round(conventional[1], 4),
                "task_cluster_ci_95_low": round(task_interval[0], 4),
                "task_cluster_ci_95_high": round(task_interval[1], 4),
                "bootstrap_replicates": BOOTSTRAP_REPLICATES,
                "bootstrap_seed": SEED,
            })
    return output


def hybrid_initial_agreement() -> dict[str, Any]:
    old_by_unit: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in read_csv(OLD_RAW):
        if row["agent_id"] != "path":
            old_by_unit[row["triplet_id"]][row["rater_id"]] = row

    new_by_unit: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in read_csv(NEW_SCORES):
        if row["batch_id"] == "formal_phase_a_path" and row["rater_id"] in {"R1", "R2"}:
            new_by_unit[row["rerating_id"]][row["rater_id"]] = row

    left: list[str] = []
    right: list[str] = []
    for unit in sorted(old_by_unit):
        pair = old_by_unit[unit]
        assert set(pair) == {"A", "B"}
        left.append(assignment(pair["A"]))
        right.append(assignment(pair["B"]))
    for unit in sorted(new_by_unit):
        pair = new_by_unit[unit]
        assert set(pair) == {"R1", "R2"}
        left.append(pair["R1"]["normalized_assignment"])
        right.append(pair["R2"]["normalized_assignment"])

    assert len(left) == 100
    agreements = sum(a == b for a, b in zip(left, right, strict=True))
    low, high = wilson(agreements, len(left))
    path_agreements = sum(
        pair["R1"]["normalized_assignment"] == pair["R2"]["normalized_assignment"]
        for pair in new_by_unit.values()
    )
    path_left = [new_by_unit[key]["R1"]["normalized_assignment"] for key in sorted(new_by_unit)]
    path_right = [new_by_unit[key]["R2"]["normalized_assignment"] for key in sorted(new_by_unit)]
    return {
        "interpretation": (
            "Post-hoc hybrid sensitivity only: historical A/B ratings for non-Path "
            "units are combined with interface-aligned R1/R2 ratings for Path. This "
            "is not a reliability estimate from one fixed rater pair."
        ),
        "units": len(left),
        "agreements": agreements,
        "agreement_rate": round(agreements / len(left), 4),
        "agreement_wilson_95_low": round(low, 4),
        "agreement_wilson_95_high": round(high, 4),
        "hybrid_six_category_kappa": round(categorical_kappa(left, right) or 0.0, 4),
        "path_units": len(new_by_unit),
        "path_agreements": path_agreements,
        "path_agreement_rate": round(path_agreements / len(new_by_unit), 4),
        "path_six_category_kappa": categorical_kappa(path_left, path_right),
        "historical_non_path_units": len(old_by_unit),
        "historical_non_path_agreements": sum(
            assignment(pair["A"]) == assignment(pair["B"])
            for pair in old_by_unit.values()
        ),
    }


def gate_assessment(rows: list[dict[str, Any]], agreement: dict[str, Any]) -> dict[str, Any]:
    overall = metrics(rows)
    agents = {
        agent: metrics([row for row in rows if row["agent_id"] == agent])
        for agent in ("reading", "quiz", "doc", "code", "path")
    }
    return {
        "formal_caveat": (
            "The frozen title gate was defined using DCR, whereas these reratings "
            "produce FM/POA/EC/ER/QG-FM. The original DCR gate cannot be formally "
            "re-evaluated by silently substituting FM."
        ),
        "conservative_fm_proxy": {
            "overall_at_or_above_0_75": overall["fm"] >= 0.75,
            "agents_at_or_above_0_70": sum(item["fm"] >= 0.70 for item in agents.values()),
            "required_agents_at_or_above_0_70": 4,
            "all_agents_at_or_above_0_60": all(item["fm"] >= 0.60 for item in agents.values()),
            "agents_over_0_15_reverse_rate": [
                agent for agent, item in agents.items() if item["er"] > 0.15
            ],
            "posthoc_hybrid_agreement_at_or_above_0_60": (
                agreement["agreement_rate"] >= 0.60
            ),
            "proxy_gate_passed": False,
        },
        "decision": (
            "The title gate remains unmet. The post-hoc analysis changes the Path "
            "interpretation but does not convert Phase A into a passing confirmatory result."
        ),
    }


def summarize_preference(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["final_decision"] for row in rows)
    non_ties = counts["profiled"] + counts["default_contract"]
    low, high = wilson(counts["profiled"], non_ties)
    return {
        "comparisons": len(rows),
        "profiled_wins": counts["profiled"],
        "default_contract_wins": counts["default_contract"],
        "ties": counts["tie"],
        "profiled_win_rate_excluding_ties": round(counts["profiled"] / non_ties, 4),
        "wilson_95_low": round(low, 4),
        "wilson_95_high": round(high, 4),
    }


def build_default_contract_sensitivity() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    historical = read_csv(UNSEEN / "deepseek_default_contract_final_comparisons.csv")
    replacements = {
        row["old_comparison_id"]: row for row in read_csv(NEW_PAIRWISE)
    }
    assert len(historical) == 90
    assert len(replacements) == 60
    used = set()
    combined = []
    for row in historical:
        item: dict[str, Any] = dict(row)
        item["analysis_source"] = "historical_code_or_unreplaced"
        replacement = replacements.get(row["comparison_id"])
        if replacement:
            used.add(row["comparison_id"])
            item["final_decision"] = replacement["final_decision"]
            item["analysis_source"] = "posthoc_leakage_controlled_doc_path"
        combined.append(item)
    assert used == set(replacements)

    quality_gated = [row for row in combined if as_bool(row["both_quality_pass"])]
    groups = {
        "all_90": summarize_preference(combined),
        "bilateral_quality_gate": summarize_preference(quality_gated),
    }
    groups["by_target_profile_quality_gated"] = {
        profile: summarize_preference(
            [row for row in quality_gated if row["target_profile_id"] == profile]
        )
        for profile in ("P1", "P2", "P3")
    }
    groups["interpretation"] = (
        "The comparison is against the system default-contract condition, which "
        "falls back toward an intermediate-level contract; it is not a label-neutral "
        "absence-of-profile baseline."
    )
    return combined, groups


def build_cross_model_sensitivity() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    batch_by_model = {
        "DeepSeek": "deepseek_unseen_doc_path",
        "Qwen": "qwen_unseen_doc_path",
    }
    replacement_rows = read_csv(NEW_FINAL)
    output = []
    summaries = {}
    for model, batch in batch_by_model.items():
        historical_path = UNSEEN / f'{model.lower()}_profiled_final_triplet_scores.csv'
        historical = read_csv(historical_path)
        replacements = {
            row["old_triplet_id"]: row
            for row in replacement_rows
            if row["batch_id"] == batch
        }
        assert len(historical) == 30
        assert len(replacements) == 20
        used = set()
        model_rows = []
        for row in historical:
            item: dict[str, Any] = dict(row)
            item["model"] = model
            item["analysis_source"] = "historical_code_or_unreplaced"
            replacement = replacements.get(row["triplet_id"])
            if replacement:
                used.add(row["triplet_id"])
                item.update({
                    "assigned_p1_candidate": "",
                    "assigned_p2_candidate": "",
                    "assigned_p3_candidate": "",
                    "true_p1_candidate": "",
                    "true_p2_candidate": "",
                    "true_p3_candidate": "",
                    "exact_profile_matches": replacement["exact_profile_matches"],
                    "full_match": replacement["full_match"],
                    "pairwise_correct": replacement["pairwise_correct"],
                    "pairwise_total": "3",
                    "pairwise_order_accuracy": replacement["pairwise_order_accuracy"],
                    "extreme_pair_correct": replacement["extreme_pair_correct"],
                    "extreme_reversed": replacement["extreme_reversed"],
                    "quality_gated_full_match": str(
                        as_bool(replacement["full_match"])
                        and as_bool(row["quality_eligible"])
                    ),
                    "quality_gated_extreme_correct": str(
                        as_bool(replacement["extreme_pair_correct"])
                        and as_bool(row["quality_eligible"])
                    ),
                    "analysis_source": "posthoc_leakage_controlled_doc_path",
                })
            model_rows.append(item)
        assert used == set(replacements)
        output.extend(model_rows)
        overall = metrics(model_rows)
        summaries[model] = {
            **overall,
            "output_quality_pass": sum(
                int(row["quality_passed_output_count"]) for row in model_rows
            ),
            "output_quality_total": 90,
        }
    return output, summaries


def main(*, emit: bool = True) -> dict[str, Any]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    rows = build_hybrid_final()
    table = metric_table(rows)
    agreement = hybrid_initial_agreement()
    default_rows, default_summary = build_default_contract_sensitivity()
    model_rows, model_summary = build_cross_model_sensitivity()
    report = {
        "status": "pass",
        "analysis_type": "posthoc_interface_aligned_sensitivity",
        "external_llm_calls_made": 0,
        "historical_files_overwritten": False,
        "replacement": "20 formal Phase A Path triplets only",
        "overall": metrics(rows),
        "agreement_sensitivity": agreement,
        "gate_assessment": gate_assessment(rows, agreement),
        "default_contract_sensitivity": default_summary,
        "cross_model_sensitivity": model_summary,
        "interpretation_boundary": [
            "The historical frozen Phase A result remains the primary recorded analysis.",
            "This sensitivity analysis aligns Path scoring material with student-visible interface content.",
            "The reraters came from the original author/rater pool and were assigned new task identifiers.",
            "The hybrid agreement statistic is not produced by one fixed rater pair across all 100 units.",
        ],
    }
    write_csv(RESULTS / "phase_a_interface_aligned_sensitivity_decisions.csv", rows)
    write_csv(RESULTS / "phase_a_interface_aligned_sensitivity_metrics.csv", table)
    write_csv(RESULTS / "default_contract_leakage_controlled_sensitivity.csv", default_rows)
    write_csv(RESULTS / "cross_model_leakage_controlled_sensitivity.csv", model_rows)
    write_json(RESULTS / "phase_a_interface_aligned_sensitivity_summary.json", report)
    if emit:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return report


if __name__ == "__main__":
    main()
