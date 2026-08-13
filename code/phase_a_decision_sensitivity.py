from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Sequence


RATER_ORDER = ("A", "B")
AGENT_ORDER = ("reading", "quiz", "doc", "code", "path")
Z_95 = 1.959963984540054


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _truth(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"expected True/False, got {value!r}")
    return normalized == "true"


def _assignment(row: dict[str, str]) -> tuple[str, str, str]:
    return tuple(
        row[field].strip().upper()
        for field in (
            "assigned_p1_candidate",
            "assigned_p2_candidate",
            "assigned_p3_candidate",
        )
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _wilson(successes: int, total: int) -> tuple[float, float]:
    estimate = successes / total
    denominator = 1 + Z_95 * Z_95 / total
    centre = (estimate + Z_95 * Z_95 / (2 * total)) / denominator
    margin = (
        Z_95
        * math.sqrt(
            estimate * (1 - estimate) / total
            + Z_95 * Z_95 / (4 * total * total)
        )
        / denominator
    )
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _task_cluster_interval(
    rows: Sequence[dict[str, Any]],
    statistic: Callable[[Sequence[dict[str, Any]]], float],
    *,
    samples: int,
    seed: int,
) -> tuple[float, float]:
    clusters: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        clusters[(row["course_name"], row["topic"])].append(row)
    labels = sorted(clusters)
    rng = random.Random(seed)
    values = []
    for _ in range(samples):
        sampled: list[dict[str, Any]] = []
        for _ in labels:
            sampled.extend(clusters[rng.choice(labels)])
        values.append(statistic(sampled))
    return _percentile(values, 0.025), _percentile(values, 0.975)


def _triplet_cluster_interval(
    rows: Sequence[dict[str, Any]],
    statistic: Callable[[Sequence[dict[str, Any]]], float],
    *,
    samples: int,
    seed: int,
) -> tuple[float, float]:
    rng = random.Random(seed)
    values = []
    for _ in range(samples):
        sampled = [rows[rng.randrange(len(rows))] for _ in rows]
        values.append(statistic(sampled))
    return _percentile(values, 0.025), _percentile(values, 0.975)


def _prepare_inputs(
    blind_rows: Sequence[dict[str, str]],
    final_rows: Sequence[dict[str, str]],
) -> tuple[dict[str, dict[str, dict[str, str]]], dict[str, dict[str, str]]]:
    by_triplet: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in blind_rows:
        rater = row["rater_id"].strip().upper()
        if rater not in RATER_ORDER:
            raise ValueError(f"unexpected Phase A rater: {rater}")
        triplet_id = row["triplet_id"]
        if rater in by_triplet[triplet_id]:
            raise ValueError(f"duplicate {rater} row for {triplet_id}")
        by_triplet[triplet_id][rater] = row
    if any(set(rows) != set(RATER_ORDER) for rows in by_triplet.values()):
        raise ValueError("each triplet must contain one A row and one B row")
    final_by_id = {row["triplet_id"]: row for row in final_rows}
    if len(final_by_id) != len(final_rows) or set(final_by_id) != set(by_triplet):
        raise ValueError("blind and final Phase A files contain different triplets")
    return by_triplet, final_by_id


def _analysis_rows(
    blind_rows: Sequence[dict[str, str]],
    final_rows: Sequence[dict[str, str]],
) -> dict[str, list[dict[str, Any]]]:
    by_triplet, final_by_id = _prepare_inputs(blind_rows, final_rows)
    analyses: dict[str, list[dict[str, Any]]] = {
        "A-only": [],
        "B-only": [],
        "A/B-consensus-only": [],
        "adjudicated-final": [],
    }
    for triplet_id in sorted(by_triplet):
        final = final_by_id[triplet_id]
        quality_eligible = _truth(final["quality_eligible"])
        for rater in RATER_ORDER:
            raw = by_triplet[triplet_id][rater]
            analyses[f"{rater}-only"].append({
                **raw,
                "quality_eligible_bool": quality_eligible,
                "full_match_bool": _truth(raw["full_match"]),
                "extreme_pair_correct_bool": _truth(raw["extreme_pair_correct"]),
                "extreme_reversed_bool": _truth(raw["extreme_reversed"]),
                "pairwise_correct_int": int(raw["pairwise_correct"]),
            })
        if _assignment(by_triplet[triplet_id]["A"]) == _assignment(by_triplet[triplet_id]["B"]):
            raw = by_triplet[triplet_id]["A"]
            analyses["A/B-consensus-only"].append({
                **raw,
                "quality_eligible_bool": quality_eligible,
                "full_match_bool": _truth(raw["full_match"]),
                "extreme_pair_correct_bool": _truth(raw["extreme_pair_correct"]),
                "extreme_reversed_bool": _truth(raw["extreme_reversed"]),
                "pairwise_correct_int": int(raw["pairwise_correct"]),
            })
        analyses["adjudicated-final"].append({
            **final,
            "quality_eligible_bool": quality_eligible,
            "full_match_bool": _truth(final["full_match"]),
            "extreme_pair_correct_bool": _truth(final["extreme_pair_correct"]),
            "extreme_reversed_bool": _truth(final["extreme_reversed"]),
            "pairwise_correct_int": int(final["pairwise_correct"]),
        })
    return analyses


def _metric_value(rows: Sequence[dict[str, Any]], metric: str) -> float:
    if metric == "FM":
        return sum(row["full_match_bool"] for row in rows) / len(rows)
    if metric == "POA":
        return sum(row["pairwise_correct_int"] for row in rows) / (3 * len(rows))
    if metric == "EC":
        return sum(row["extreme_pair_correct_bool"] for row in rows) / len(rows)
    if metric == "ER":
        return sum(row["extreme_reversed_bool"] for row in rows) / len(rows)
    if metric == "QG-FM":
        return sum(
            row["full_match_bool"] and row["quality_eligible_bool"] for row in rows
        ) / len(rows)
    raise ValueError(f"unknown metric: {metric}")


def analyze(
    blind_rows: Sequence[dict[str, str]],
    final_rows: Sequence[dict[str, str]],
    *,
    bootstrap_samples: int = 10_000,
    seed: int = 20260813,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    analyses = _analysis_rows(blind_rows, final_rows)
    metrics: list[dict[str, Any]] = []
    for analysis_index, (analysis, rows) in enumerate(analyses.items()):
        groups = [("overall", "ALL", rows)]
        groups.extend(
            ("agent", agent, [row for row in rows if row["agent_id"] == agent])
            for agent in AGENT_ORDER
        )
        for group_index, (group_type, group_key, selected) in enumerate(groups):
            if not selected:
                continue
            for metric_index, metric in enumerate(("FM", "POA", "EC", "ER", "QG-FM")):
                if metric == "POA":
                    numerator = sum(row["pairwise_correct_int"] for row in selected)
                    denominator = 3 * len(selected)
                    conventional_method = "triplet bootstrap"
                    conventional_low, conventional_high = _triplet_cluster_interval(
                        selected,
                        lambda sample: _metric_value(sample, metric),
                        samples=bootstrap_samples,
                        seed=seed + analysis_index * 1000 + group_index * 100 + metric_index,
                    )
                else:
                    denominator = len(selected)
                    numerator = round(_metric_value(selected, metric) * denominator)
                    conventional_method = "Wilson score"
                    conventional_low, conventional_high = _wilson(numerator, denominator)
                cluster_low, cluster_high = _task_cluster_interval(
                    selected,
                    lambda sample, name=metric: _metric_value(sample, name),
                    samples=bootstrap_samples,
                    seed=seed + 50_000 + analysis_index * 1000 + group_index * 100 + metric_index,
                )
                metrics.append({
                    "analysis": analysis,
                    "group_type": group_type,
                    "group_key": group_key,
                    "triplet_count": len(selected),
                    "task_cluster_count": len({(row["course_name"], row["topic"]) for row in selected}),
                    "metric": metric,
                    "numerator": numerator,
                    "denominator": denominator,
                    "estimate": round(_metric_value(selected, metric), 6),
                    "conventional_ci_method": conventional_method,
                    "conventional_ci_95_low": round(conventional_low, 6),
                    "conventional_ci_95_high": round(conventional_high, 6),
                    "task_cluster_ci_95_low": round(cluster_low, 6),
                    "task_cluster_ci_95_high": round(cluster_high, 6),
                    "bootstrap_samples": bootstrap_samples,
                    "random_seed_base": seed,
                })

    by_triplet, final_by_id = _prepare_inputs(blind_rows, final_rows)
    alignment: list[dict[str, Any]] = []
    for scope, triplet_ids in (
        ("all-final-decisions", sorted(by_triplet)),
        (
            "adjudicated-only",
            sorted(
                triplet_id
                for triplet_id, row in final_by_id.items()
                if row["decision_source"] == "adjudication"
            ),
        ),
    ):
        for rater in RATER_ORDER:
            agreements = sum(
                _assignment(by_triplet[triplet_id][rater])
                == _assignment(final_by_id[triplet_id])
                for triplet_id in triplet_ids
            )
            low, high = _wilson(agreements, len(triplet_ids))
            alignment.append({
                "scope": scope,
                "rater": rater,
                "triplet_count": len(triplet_ids),
                "full_assignment_agreements_with_final": agreements,
                "agreement_rate": round(agreements / len(triplet_ids), 6),
                "wilson_ci_95_low": round(low, 6),
                "wilson_ci_95_high": round(high, 6),
            })
    return metrics, alignment


def run_analysis(
    blind_scores_path: Path,
    final_decisions_path: Path,
    output_dir: Path,
    *,
    bootstrap_samples: int = 10_000,
    seed: int = 20260813,
) -> dict[str, Path]:
    metrics, alignment = analyze(
        _read_csv(blind_scores_path),
        _read_csv(final_decisions_path),
        bootstrap_samples=bootstrap_samples,
        seed=seed,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "metrics": output_dir / "formal_phase_a_decision_sensitivity.csv",
        "alignment": output_dir / "formal_phase_a_final_alignment.csv",
        "summary": output_dir / "formal_phase_a_decision_sensitivity.json",
    }
    _write_csv(paths["metrics"], metrics)
    _write_csv(paths["alignment"], alignment)
    paths["summary"].write_text(
        json.dumps({
            "analysis_note": (
                "A-only and B-only use each initial rating independently. "
                "A/B-consensus-only contains only triplets with identical complete "
                "assignments and is a selected subset, not an estimate for all Phase A "
                "triplets. Adjudicated-final is the historical final decision set."
            ),
            "bootstrap_unit": "course-topic task cluster",
            "bootstrap_samples": bootstrap_samples,
            "random_seed_base": seed,
            "external_llm_api_calls": 0,
            "inputs": {
                "blind_scores_sha256": _sha256(blind_scores_path),
                "final_decisions_sha256": _sha256(final_decisions_path),
            },
            "metrics": metrics,
            "final_alignment": alignment,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return paths
