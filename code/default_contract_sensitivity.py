from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Sequence


REQUIRED_FIELDS = {
    "final_decision",
    "both_quality_pass",
    "default_contract_condition_id",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_FIELDS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"default-contract comparisons missing fields: {sorted(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError("default-contract comparisons are empty")
    return rows


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


def _task_id(row: dict[str, str]) -> str:
    return row["default_contract_condition_id"].split("|", 1)[0]


def _cluster_counts(
    rows: Sequence[dict[str, str]], key: Callable[[dict[str, str]], str]
) -> list[tuple[int, int, int]]:
    clusters: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        clusters[key(row)].append(row)
    counts = []
    for cluster_rows in clusters.values():
        decisions = Counter(row["final_decision"] for row in cluster_rows)
        unknown = set(decisions) - {"profiled", "default_contract", "tie"}
        if unknown:
            raise ValueError(f"unknown final decisions: {sorted(unknown)}")
        counts.append((
            decisions["profiled"], decisions["default_contract"], decisions["tie"]
        ))
    return counts


def _cluster_bootstrap_interval(
    counts: Sequence[tuple[int, int, int]], *, samples: int, seed: int
) -> tuple[float, float]:
    if samples <= 0:
        raise ValueError("bootstrap samples must be positive")
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        sampled = [counts[rng.randrange(len(counts))] for _ in counts]
        profiled = sum(row[0] for row in sampled)
        default_contract = sum(row[1] for row in sampled)
        if profiled + default_contract:
            estimates.append(profiled / (profiled + default_contract))
    if not estimates:
        raise ValueError("cluster bootstrap has no non-tied comparisons")
    return _percentile(estimates, 0.025), _percentile(estimates, 0.975)


def _exact_cluster_sign_flip_p(counts: Sequence[tuple[int, int, int]]) -> float | None:
    weights = [
        profiled - default_contract
        for profiled, default_contract, _ in counts
        if profiled != default_contract
    ]
    if not weights:
        return None
    observed = abs(sum(weights))
    distribution = Counter({0: 1})
    for weight in weights:
        updated: Counter[int] = Counter()
        for total, combinations in distribution.items():
            updated[total + weight] += combinations
            updated[total - weight] += combinations
        distribution = updated
    extreme = sum(count for total, count in distribution.items() if abs(total) >= observed)
    return extreme / (2 ** len(weights))


def _summary_row(
    rows: Sequence[dict[str, str]],
    *,
    scope: str,
    cluster_level: str,
    key: Callable[[dict[str, str]], str],
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    counts = _cluster_counts(rows, key)
    profiled = sum(row[0] for row in counts)
    default_contract = sum(row[1] for row in counts)
    ties = sum(row[2] for row in counts)
    if not profiled + default_contract:
        raise ValueError("sensitivity analysis requires at least one non-tied comparison")
    low, high = _cluster_bootstrap_interval(
        counts, samples=bootstrap_samples, seed=seed
    )
    return {
        "scope": scope,
        "cluster_level": cluster_level,
        "comparison_rows": len(rows),
        "cluster_count": len(counts),
        "profiled_wins": profiled,
        "default_contract_wins": default_contract,
        "ties": ties,
        "profiled_win_rate_excluding_ties": profiled / (profiled + default_contract),
        "cluster_bootstrap_ci_95_low": low,
        "cluster_bootstrap_ci_95_high": high,
        "exact_cluster_sign_flip_p": _exact_cluster_sign_flip_p(counts),
        "bootstrap_samples": bootstrap_samples,
        "random_seed": seed,
    }


def analyze_default_contract_cluster_sensitivity(
    comparisons_path: Path,
    output_csv: Path,
    output_json: Path,
    *,
    bootstrap_samples: int = 10_000,
    seed: int = 20260803,
    force: bool = False,
) -> dict[str, Any]:
    parts = comparisons_path.parts
    portable_input_path = (
        Path(*parts[parts.index("data"):]).as_posix()
        if "data" in parts
        else comparisons_path.name
    )
    for path in (output_csv, output_json):
        if path.exists() and not force:
            raise FileExistsError(f"output already exists: {path}")
    rows = _read_csv(comparisons_path)
    gated = [row for row in rows if row["both_quality_pass"].strip().lower() == "true"]
    analyses = []
    for scope, scope_rows in (("all", rows), ("quality_gated", gated)):
        analyses.append(_summary_row(
            scope_rows,
            scope=scope,
            cluster_level="shared_default_output",
            key=lambda row: row["default_contract_condition_id"],
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        ))
        analyses.append(_summary_row(
            scope_rows,
            scope=scope,
            cluster_level="task",
            key=_task_id,
            bootstrap_samples=bootstrap_samples,
            seed=seed + 1,
        ))

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(analyses[0]))
        writer.writeheader()
        writer.writerows(analyses)
    payload = {
        "analysis": "cluster sensitivity for profiled-versus-default-contract preferences",
        "input_path": portable_input_path,
        "input_sha256": _sha256(comparisons_path),
        "analysis_note": (
            "Point estimates retain comparison rows as the estimand. Confidence intervals "
            "resample shared-default-output clusters, and exact sign-flip tests reverse all "
            "preferences within a cluster together. Task-level clustering is a stricter "
            "sensitivity analysis for dependencies shared across agents."
        ),
        "external_llm_calls_made": 0,
        "analyses": analyses,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
