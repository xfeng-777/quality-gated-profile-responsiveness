from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Sequence


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]], *, force: bool) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    if path.exists() and not force:
        raise FileExistsError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any], *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _truth(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"expected True/False, got {value!r}")
    return normalized == "true"


def _yes(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"yes", "no"}:
        raise ValueError(f"expected yes/no, got {value!r}")
    return normalized == "yes"


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _bootstrap_difference(
    differences: Sequence[float], *, samples: int, seed: int
) -> tuple[float, float]:
    if not differences:
        raise ValueError("paired bootstrap requires at least one difference")
    rng = random.Random(seed)
    estimates = [
        sum(differences[rng.randrange(len(differences))] for _ in differences)
        / len(differences)
        for _ in range(samples)
    ]
    return _percentile(estimates, 0.025), _percentile(estimates, 0.975)


def exact_two_sided_sign_p(left_only: int, right_only: int) -> float | None:
    discordant = left_only + right_only
    if discordant == 0:
        return None
    tail = sum(
        math.comb(discordant, index) for index in range(min(left_only, right_only) + 1)
    ) / (2**discordant)
    return min(1.0, 2 * tail)


def _group_pairs(
    rows: Sequence[dict[str, Any]],
) -> list[tuple[str, str, list[dict[str, Any]]]]:
    groups: list[tuple[str, str, list[dict[str, Any]]]] = [("overall", "ALL", list(rows))]
    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_agent[row["agent_id"]].append(row)
    for agent_id in sorted(by_agent):
        groups.append(("agent", agent_id, by_agent[agent_id]))
    return groups


def _binary_summary(
    rows: Sequence[dict[str, Any]],
    *,
    level: str,
    group_type: str,
    group_key: str,
    metric: str,
    deepseek_field: str,
    qwen_field: str,
    bootstrap_samples: int,
    seed: int,
    lower_is_better: bool = False,
) -> dict[str, Any]:
    deepseek_values = [bool(row[deepseek_field]) for row in rows]
    qwen_values = [bool(row[qwen_field]) for row in rows]
    differences = [int(qwen) - int(deepseek) for deepseek, qwen in zip(deepseek_values, qwen_values)]
    qwen_only = sum(not deepseek and qwen for deepseek, qwen in zip(deepseek_values, qwen_values))
    deepseek_only = sum(deepseek and not qwen for deepseek, qwen in zip(deepseek_values, qwen_values))
    both_pass = sum(deepseek and qwen for deepseek, qwen in zip(deepseek_values, qwen_values))
    both_fail = sum(not deepseek and not qwen for deepseek, qwen in zip(deepseek_values, qwen_values))
    low, high = _bootstrap_difference(
        differences,
        samples=bootstrap_samples,
        seed=seed,
    )
    return {
        "analysis_level": level,
        "group_type": group_type,
        "group_key": group_key,
        "metric": metric,
        "n_pairs": len(rows),
        "deepseek_numerator": sum(deepseek_values),
        "deepseek_estimate": sum(deepseek_values) / len(rows),
        "qwen_numerator": sum(qwen_values),
        "qwen_estimate": sum(qwen_values) / len(rows),
        "qwen_minus_deepseek": sum(differences) / len(rows),
        "paired_bootstrap_ci_95_low": low,
        "paired_bootstrap_ci_95_high": high,
        "both_positive": both_pass,
        "both_negative": both_fail,
        "qwen_only_positive": qwen_only,
        "deepseek_only_positive": deepseek_only,
        "paired_outcome_stability_rate": (both_pass + both_fail) / len(rows),
        "exact_mcnemar_p": exact_two_sided_sign_p(deepseek_only, qwen_only),
        "lower_is_better": lower_is_better,
        "bootstrap_samples": bootstrap_samples,
    }


def _continuous_summary(
    rows: Sequence[dict[str, Any]],
    *,
    level: str,
    group_type: str,
    group_key: str,
    metric: str,
    deepseek_field: str,
    qwen_field: str,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    deepseek_values = [float(row[deepseek_field]) for row in rows]
    qwen_values = [float(row[qwen_field]) for row in rows]
    differences = [qwen - deepseek for deepseek, qwen in zip(deepseek_values, qwen_values)]
    qwen_higher = sum(value > 0 for value in differences)
    deepseek_higher = sum(value < 0 for value in differences)
    ties = sum(math.isclose(value, 0.0) for value in differences)
    low, high = _bootstrap_difference(
        differences,
        samples=bootstrap_samples,
        seed=seed,
    )
    return {
        "analysis_level": level,
        "group_type": group_type,
        "group_key": group_key,
        "metric": metric,
        "n_pairs": len(rows),
        "deepseek_numerator": "",
        "deepseek_estimate": sum(deepseek_values) / len(rows),
        "qwen_numerator": "",
        "qwen_estimate": sum(qwen_values) / len(rows),
        "qwen_minus_deepseek": sum(differences) / len(rows),
        "paired_bootstrap_ci_95_low": low,
        "paired_bootstrap_ci_95_high": high,
        "both_positive": "",
        "both_negative": ties,
        "qwen_only_positive": qwen_higher,
        "deepseek_only_positive": deepseek_higher,
        "paired_outcome_stability_rate": ties / len(rows),
        "exact_mcnemar_p": exact_two_sided_sign_p(deepseek_higher, qwen_higher),
        "lower_is_better": False,
        "bootstrap_samples": bootstrap_samples,
    }


def _triplet_pairs(
    deepseek_rows: Sequence[dict[str, str]], qwen_rows: Sequence[dict[str, str]]
) -> list[dict[str, Any]]:
    def key(row: dict[str, str]) -> tuple[str, str, str, str]:
        return row["course_name"], row["topic"], row["agent_id"], row["repeat"]

    deepseek = {key(row): row for row in deepseek_rows}
    qwen = {key(row): row for row in qwen_rows}
    if len(deepseek) != len(deepseek_rows) or len(qwen) != len(qwen_rows):
        raise ValueError("triplet comparison keys must be unique")
    if set(deepseek) != set(qwen):
        raise ValueError("DeepSeek and Qwen triplet conditions differ")
    pairs: list[dict[str, Any]] = []
    for condition in sorted(deepseek):
        d_row, q_row = deepseek[condition], qwen[condition]
        pairs.append({
            "course_name": condition[0],
            "topic": condition[1],
            "agent_id": condition[2].strip().lower(),
            "repeat": condition[3],
            "deepseek_triplet_id": d_row["triplet_id"],
            "qwen_triplet_id": q_row["triplet_id"],
            "deepseek_full_match": _truth(d_row["full_match"]),
            "qwen_full_match": _truth(q_row["full_match"]),
            "deepseek_extreme_pair_correct": _truth(d_row["extreme_pair_correct"]),
            "qwen_extreme_pair_correct": _truth(q_row["extreme_pair_correct"]),
            "deepseek_quality_eligible": _truth(d_row["quality_eligible"]),
            "qwen_quality_eligible": _truth(q_row["quality_eligible"]),
            "deepseek_quality_gated_full_match": _truth(d_row["quality_gated_full_match"]),
            "qwen_quality_gated_full_match": _truth(q_row["quality_gated_full_match"]),
            "deepseek_quality_gated_extreme_correct": _truth(d_row["quality_gated_extreme_correct"]),
            "qwen_quality_gated_extreme_correct": _truth(q_row["quality_gated_extreme_correct"]),
            "deepseek_pairwise_order_accuracy": float(d_row["pairwise_order_accuracy"]),
            "qwen_pairwise_order_accuracy": float(q_row["pairwise_order_accuracy"]),
        })
    return pairs


def _domain_rows_by_condition(review_path: Path, mapping_path: Path) -> dict[str, dict[str, str]]:
    reviews = {row["review_id"]: row for row in _read_csv(review_path)}
    mapping = _read_jsonl(mapping_path)
    if set(reviews) != {row["review_id"] for row in mapping}:
        raise ValueError(f"domain reviews and mapping differ: {review_path}")
    return {row["condition_id"]: reviews[row["review_id"]] for row in mapping}


def _domain_pairs(
    deepseek_review_path: Path,
    deepseek_mapping_path: Path,
    qwen_review_path: Path,
    qwen_mapping_path: Path,
) -> list[dict[str, Any]]:
    deepseek = _domain_rows_by_condition(deepseek_review_path, deepseek_mapping_path)
    qwen = _domain_rows_by_condition(qwen_review_path, qwen_mapping_path)
    if set(deepseek) != set(qwen):
        raise ValueError("DeepSeek and Qwen domain conditions differ")
    pairs: list[dict[str, Any]] = []
    for condition_id in sorted(deepseek):
        d_row, q_row = deepseek[condition_id], qwen[condition_id]
        task_id, profile_id, agent_id, repeat = condition_id.split("|")
        pairs.append({
            "condition_id": condition_id,
            "task_id": task_id,
            "profile_id": profile_id,
            "agent_id": agent_id,
            "repeat": repeat,
            "course_name": d_row["course_name"],
            "topic": d_row["topic"],
            "deepseek_factual_correctness": d_row["final_factual_correctness"],
            "qwen_factual_correctness": q_row["final_factual_correctness"],
            "deepseek_factual_pass": d_row["final_factual_correctness"] == "pass",
            "qwen_factual_pass": q_row["final_factual_correctness"] == "pass",
            "deepseek_major_error": d_row["final_factual_correctness"] == "major_error",
            "qwen_major_error": q_row["final_factual_correctness"] == "major_error",
            "deepseek_quality_floor_pass": _yes(d_row["final_quality_floor_pass"]),
            "qwen_quality_floor_pass": _yes(q_row["final_quality_floor_pass"]),
            "deepseek_answer_consistency": d_row["final_answer_consistency"],
            "qwen_answer_consistency": q_row["final_answer_consistency"],
            "deepseek_structurally_valid": d_row["final_executable_or_structurally_valid"],
            "qwen_structurally_valid": q_row["final_executable_or_structurally_valid"],
        })
    return pairs


def compare_generation_models(
    deepseek_triplets: Path,
    qwen_triplets: Path,
    deepseek_domain: Path,
    deepseek_domain_mapping: Path,
    qwen_domain: Path,
    qwen_domain_mapping: Path,
    triplet_pairs_output: Path,
    domain_pairs_output: Path,
    summary_csv: Path,
    summary_json: Path,
    *,
    bootstrap_samples: int = 10_000,
    seed: int = 20260803,
    force: bool = False,
) -> dict[str, Any]:
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")
    inputs = [
        deepseek_triplets, qwen_triplets, deepseek_domain, deepseek_domain_mapping,
        qwen_domain, qwen_domain_mapping,
    ]
    triplet_pairs = _triplet_pairs(_read_csv(deepseek_triplets), _read_csv(qwen_triplets))
    domain_pairs = _domain_pairs(
        deepseek_domain, deepseek_domain_mapping, qwen_domain, qwen_domain_mapping
    )
    if len(triplet_pairs) != 30 or len(domain_pairs) != 90:
        raise ValueError(
            f"expected 30 triplet and 90 domain pairs, got {len(triplet_pairs)} and {len(domain_pairs)}"
        )

    summary_rows: list[dict[str, Any]] = []
    triplet_binary_metrics = {
        "FM": ("deepseek_full_match", "qwen_full_match"),
        "EC": ("deepseek_extreme_pair_correct", "qwen_extreme_pair_correct"),
        "quality_eligible": ("deepseek_quality_eligible", "qwen_quality_eligible"),
        "QG-FM": ("deepseek_quality_gated_full_match", "qwen_quality_gated_full_match"),
        "QG-EC": ("deepseek_quality_gated_extreme_correct", "qwen_quality_gated_extreme_correct"),
    }
    group_index = 0
    for group_type, group_key, rows in _group_pairs(triplet_pairs):
        for metric, fields in triplet_binary_metrics.items():
            summary_rows.append(_binary_summary(
                rows,
                level="triplet",
                group_type=group_type,
                group_key=group_key,
                metric=metric,
                deepseek_field=fields[0],
                qwen_field=fields[1],
                bootstrap_samples=bootstrap_samples,
                seed=seed + group_index,
            ))
            group_index += 1
        summary_rows.append(_continuous_summary(
            rows,
            level="triplet",
            group_type=group_type,
            group_key=group_key,
            metric="POA",
            deepseek_field="deepseek_pairwise_order_accuracy",
            qwen_field="qwen_pairwise_order_accuracy",
            bootstrap_samples=bootstrap_samples,
            seed=seed + group_index,
        ))
        group_index += 1

    domain_metrics = {
        "factual_pass": ("deepseek_factual_pass", "qwen_factual_pass", False),
        "major_error": ("deepseek_major_error", "qwen_major_error", True),
        "quality_floor_pass": ("deepseek_quality_floor_pass", "qwen_quality_floor_pass", False),
    }
    for group_type, group_key, rows in _group_pairs(domain_pairs):
        for metric, fields in domain_metrics.items():
            summary_rows.append(_binary_summary(
                rows,
                level="domain_output",
                group_type=group_type,
                group_key=group_key,
                metric=metric,
                deepseek_field=fields[0],
                qwen_field=fields[1],
                bootstrap_samples=bootstrap_samples,
                seed=seed + group_index,
                lower_is_better=fields[2],
            ))
            group_index += 1
        if group_key in {"ALL", "code"}:
            applicable = [
                row for row in rows
                if row["deepseek_answer_consistency"] != "na"
                and row["qwen_answer_consistency"] != "na"
            ]
            if applicable:
                enriched = [
                    {
                        **row,
                        "deepseek_answer_consistency_pass": _yes(row["deepseek_answer_consistency"]),
                        "qwen_answer_consistency_pass": _yes(row["qwen_answer_consistency"]),
                        "deepseek_structurally_valid_pass": _yes(row["deepseek_structurally_valid"]),
                        "qwen_structurally_valid_pass": _yes(row["qwen_structurally_valid"]),
                    }
                    for row in applicable
                ]
                for metric, fields in {
                    "answer_consistency": (
                        "deepseek_answer_consistency_pass", "qwen_answer_consistency_pass"
                    ),
                    "structurally_valid": (
                        "deepseek_structurally_valid_pass", "qwen_structurally_valid_pass"
                    ),
                }.items():
                    summary_rows.append(_binary_summary(
                        enriched,
                        level="domain_output",
                        group_type=group_type,
                        group_key=group_key,
                        metric=metric,
                        deepseek_field=fields[0],
                        qwen_field=fields[1],
                        bootstrap_samples=bootstrap_samples,
                        seed=seed + group_index,
                    ))
                    group_index += 1

    _write_csv(triplet_pairs_output, triplet_pairs, force=force)
    _write_csv(domain_pairs_output, domain_pairs, force=force)
    _write_csv(summary_csv, summary_rows, force=force)
    payload = {
        "schema_version": 1,
        "analysis": "paired DeepSeek-v4-Pro versus Qwen3.7-Max generation-model stability",
        "bootstrap_samples": bootstrap_samples,
        "random_seed": seed,
        "triplet_pair_count": len(triplet_pairs),
        "domain_output_pair_count": len(domain_pairs),
        "input_sha256": {str(path): _sha256(path) for path in inputs},
        "summary": summary_rows,
        "interpretation_note": (
            "Rows are paired by frozen task/profile/agent conditions. Exact McNemar tests use "
            "discordant binary pairs; POA uses an exact two-sided sign test on non-tied paired "
            "differences. Paired bootstrap intervals resample frozen condition pairs."
        ),
        "external_llm_calls_made": 0,
    }
    _write_json(summary_json, payload, force=force)
    return {
        "triplet_pair_count": len(triplet_pairs),
        "domain_output_pair_count": len(domain_pairs),
        "summary_rows": len(summary_rows),
        "triplet_pairs_output": str(triplet_pairs_output),
        "domain_pairs_output": str(domain_pairs_output),
        "summary_csv": str(summary_csv),
        "summary_json": str(summary_json),
        "external_llm_calls_made": 0,
    }
