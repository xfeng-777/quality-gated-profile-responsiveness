from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


AGENT_ORDER = ("reading", "quiz", "doc", "code", "path")
ASSIGNMENT_FIELDS = (
    "assigned_p1_candidate",
    "assigned_p2_candidate",
    "assigned_p3_candidate",
)
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


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between 0 and 1")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def wilson_interval(successes: int, total: int, z: float = Z_95) -> tuple[float, float]:
    if total <= 0:
        raise ValueError("total must be positive")
    if successes < 0 or successes > total:
        raise ValueError("successes must be between zero and total")
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    half_width = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return max(0.0, centre - half_width), min(1.0, centre + half_width)


def cohen_kappa(pairs: Sequence[tuple[tuple[str, ...], tuple[str, ...]]]) -> float | None:
    if not pairs:
        return None
    categories = {value for pair in pairs for value in pair}
    observed = sum(left == right for left, right in pairs) / len(pairs)
    expected = sum(
        sum(left == category for left, _ in pairs) / len(pairs)
        * sum(right == category for _, right in pairs) / len(pairs)
        for category in categories
    )
    if math.isclose(expected, 1.0):
        return None
    return (observed - expected) / (1 - expected)


def _group_seed(seed: int, label: str) -> int:
    suffix = int(hashlib.sha256(label.encode("utf-8")).hexdigest()[:16], 16)
    return seed ^ suffix


def _bootstrap_interval(
    records: Sequence[Any],
    statistic: Callable[[Sequence[Any]], float | None],
    *,
    samples: int,
    seed: int,
) -> tuple[float, float, int]:
    if not records:
        raise ValueError("bootstrap requires at least one record")
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(samples):
        resample = [records[rng.randrange(len(records))] for _ in records]
        value = statistic(resample)
        if value is not None and math.isfinite(value):
            values.append(value)
    if not values:
        raise ValueError("all bootstrap replicates were undefined")
    return _percentile(values, 0.025), _percentile(values, 0.975), len(values)


def _groups(rows: Sequence[dict[str, str]]) -> Iterable[tuple[str, str, list[dict[str, str]]]]:
    yield "overall", "ALL", list(rows)
    by_agent: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_agent[row["agent_id"].strip().lower()].append(row)
    unexpected = sorted(set(by_agent) - set(AGENT_ORDER))
    if unexpected:
        raise ValueError(f"unexpected agent IDs: {unexpected}")
    for agent in AGENT_ORDER:
        if agent not in by_agent:
            raise ValueError(f"missing agent rows: {agent}")
        yield "agent", agent, by_agent[agent]


def analyze_metric_uncertainty(
    final_rows: Sequence[dict[str, str]],
    *,
    bootstrap_samples: int = 10_000,
    seed: int = 20260802,
) -> list[dict[str, Any]]:
    if len({row["triplet_id"] for row in final_rows}) != len(final_rows):
        raise ValueError("final decisions must contain one row per triplet")
    result: list[dict[str, Any]] = []
    binary_metrics = {
        "FM": "full_match",
        "EC": "extreme_pair_correct",
        "ER": "extreme_reversed",
        "QG-FM": "quality_gated_full_match",
    }
    for group_type, group_key, rows in _groups(final_rows):
        n = len(rows)
        for metric, field in binary_metrics.items():
            successes = sum(_truth(row[field]) for row in rows)
            low, high = wilson_interval(successes, n)
            result.append({
                "group_type": group_type,
                "group_key": group_key,
                "triplet_count": n,
                "metric": metric,
                "numerator": successes,
                "denominator": n,
                "estimate": successes / n,
                "ci_method": "Wilson score",
                "ci_95_low": low,
                "ci_95_high": high,
                "bootstrap_valid_replicates": "",
            })

        pair_records = [
            (int(row["pairwise_correct"]), int(row["pairwise_total"]))
            for row in rows
        ]
        if any(total != 3 for _, total in pair_records):
            raise ValueError("each triplet must contribute exactly three pairwise comparisons")

        def pairwise_stat(records: Sequence[tuple[int, int]]) -> float:
            return sum(correct for correct, _ in records) / sum(total for _, total in records)

        point = pairwise_stat(pair_records)
        low, high, valid = _bootstrap_interval(
            pair_records,
            pairwise_stat,
            samples=bootstrap_samples,
            seed=_group_seed(seed, f"metric:{group_type}:{group_key}:POA"),
        )
        result.append({
            "group_type": group_type,
            "group_key": group_key,
            "triplet_count": n,
            "metric": "POA",
            "numerator": sum(correct for correct, _ in pair_records),
            "denominator": sum(total for _, total in pair_records),
            "estimate": point,
            "ci_method": f"triplet cluster bootstrap ({bootstrap_samples} replicates)",
            "ci_95_low": low,
            "ci_95_high": high,
            "bootstrap_valid_replicates": valid,
        })
    return result


def _pair_raters(blind_rows: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    by_triplet: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in blind_rows:
        by_triplet[row["triplet_id"]].append(row)
    paired: list[dict[str, Any]] = []
    for triplet_id, rows in sorted(by_triplet.items()):
        if len(rows) != 2 or len({row["rater_id"] for row in rows}) != 2:
            raise ValueError(f"triplet {triplet_id} must have exactly two distinct raters")
        rows = sorted(rows, key=lambda row: row["rater_id"])
        left, right = rows
        if left["agent_id"].strip().lower() != right["agent_id"].strip().lower():
            raise ValueError(f"triplet {triplet_id} has inconsistent agent IDs")
        paired.append({
            "triplet_id": triplet_id,
            "agent_id": left["agent_id"].strip().lower(),
            "left_id": left["rater_id"],
            "right_id": right["rater_id"],
            "left_assignment": tuple(left[field].strip().upper() for field in ASSIGNMENT_FIELDS),
            "right_assignment": tuple(right[field].strip().upper() for field in ASSIGNMENT_FIELDS),
            "left_low": left["confidence"].strip().lower() == "low",
            "right_low": right["confidence"].strip().lower() == "low",
            "left_indistinguishable": left["indistinguishable"].strip().lower() == "yes",
            "right_indistinguishable": right["indistinguishable"].strip().lower() == "yes",
        })
    return paired


def analyze_rater_reliability(
    blind_rows: Sequence[dict[str, str]],
    final_rows: Sequence[dict[str, str]],
    *,
    bootstrap_samples: int = 10_000,
    seed: int = 20260802,
) -> list[dict[str, Any]]:
    paired = _pair_raters(blind_rows)
    final_by_id = {row["triplet_id"]: row for row in final_rows}
    if set(final_by_id) != {row["triplet_id"] for row in paired}:
        raise ValueError("blind scores and final decisions contain different triplet IDs")
    result: list[dict[str, Any]] = []
    for group_type, group_key, rows in _groups(paired):
        n = len(rows)
        agreement_pairs = [
            (row["left_assignment"], row["right_assignment"])
            for row in rows
        ]
        agreements = sum(left == right for left, right in agreement_pairs)
        agreement_low, agreement_high = wilson_interval(agreements, n)
        kappa = cohen_kappa(agreement_pairs)
        kappa_low, kappa_high, valid = _bootstrap_interval(
            agreement_pairs,
            cohen_kappa,
            samples=bootstrap_samples,
            seed=_group_seed(seed, f"reliability:{group_type}:{group_key}:kappa"),
        )
        adjudicated = sum(
            final_by_id[row["triplet_id"]]["decision_source"] == "adjudication"
            for row in rows
        )
        result.append({
            "group_type": group_type,
            "group_key": group_key,
            "triplet_count": n,
            "full_assignment_agreements": agreements,
            "full_assignment_agreement_rate": agreements / n,
            "agreement_ci_95_low": agreement_low,
            "agreement_ci_95_high": agreement_high,
            "cohen_kappa": kappa,
            "kappa_ci_95_low": kappa_low,
            "kappa_ci_95_high": kappa_high,
            "kappa_bootstrap_valid_replicates": valid,
            "assignment_disagreement_triplets": n - agreements,
            "either_low_confidence_triplets": sum(
                row["left_low"] or row["right_low"] for row in rows
            ),
            "either_indistinguishable_triplets": sum(
                row["left_indistinguishable"] or row["right_indistinguishable"]
                for row in rows
            ),
            "rater_a_low_confidence_rows": sum(row["left_low"] for row in rows),
            "rater_b_low_confidence_rows": sum(row["right_low"] for row in rows),
            "rater_a_indistinguishable_rows": sum(
                row["left_indistinguishable"] for row in rows
            ),
            "rater_b_indistinguishable_rows": sum(
                row["right_indistinguishable"] for row in rows
            ),
            "adjudicated_triplets": adjudicated,
            "adjudication_rate": adjudicated / n,
        })
    return result


def _rounded(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            key: round(value, 6) if isinstance(value, float) else value
            for key, value in row.items()
        }
        for row in rows
    ]


def _metric_lookup(rows: Sequence[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(row["group_key"], row["metric"]): row for row in rows}


def _ci_cell(row: dict[str, Any]) -> str:
    return (
        f'{row["estimate"]:.2f} '
        f'[{row["ci_95_low"]:.2f}, {row["ci_95_high"]:.2f}]'
    )


def render_markdown(
    metric_rows: Sequence[dict[str, Any]],
    reliability_rows: Sequence[dict[str, Any]],
    *,
    bootstrap_samples: int,
    seed: int,
    blind_scores_path: Path,
    final_decisions_path: Path,
) -> str:
    metrics = _metric_lookup(metric_rows)
    reliability = {row["group_key"]: row for row in reliability_rows}
    labels = {
        "ALL": "全系统",
        "reading": "Reading",
        "quiz": "Quiz",
        "doc": "Doc",
        "code": "Code",
        "path": "Path",
    }
    lines = [
        "# 正式阶段 A 一致性与统计不确定性分析",
        "",
        "> 日期：2026-08-02  ",
        "> 分析范围：正式阶段 A，100 个三画像三元组  ",
        f"> 随机种子：`{seed}`；bootstrap：`{bootstrap_samples}` 次  ",
        "> 外部 LLM API 调用：0（仅指本统计脚本）",
        "",
        "## 1. 分析口径",
        "",
        "分析单位为同一任务、同一 Agent 下的 P1/P2/P3 三输出组，而不是 300 条单独输出。FM、EC、ER 和 QG-FM 的 95% 置信区间采用 Wilson score 区间；POA 按三元组整组重采样，以保留每组三个成对判断的相关性。Cohen's kappa 将三画像完整排列视为六分类标签，并以三元组 bootstrap 计算 95% 置信区间。所有 bootstrap 均使用固定随机种子。",
        "",
        "## 2. 画像响应性点估计与 95% 置信区间",
        "",
        "| Agent/汇总 | 三元组数 | FM [95% CI] | POA [95% CI] | EC [95% CI] | ER [95% CI] | QG-FM [95% CI] |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key in labels:
        n = metrics[(key, "FM")]["triplet_count"]
        lines.append(
            f'| {labels[key]} | {n} | {_ci_cell(metrics[(key, "FM")])} | '
            f'{_ci_cell(metrics[(key, "POA")])} | {_ci_cell(metrics[(key, "EC")])} | '
            f'{_ci_cell(metrics[(key, "ER")])} | {_ci_cell(metrics[(key, "QG-FM")])} |'
        )
    lines.extend([
        "",
        "## 3. A/B 评分者一致性",
        "",
        "| Agent/汇总 | 三元组数 | 完整排列一致率 [95% CI] | Cohen's kappa [95% CI] | 排列分歧 | 低置信触发 | 不可区分触发 | 进入裁决 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for key in labels:
        row = reliability[key]
        lines.append(
            f'| {labels[key]} | {row["triplet_count"]} | '
            f'{row["full_assignment_agreement_rate"]:.2f} '
            f'[{row["agreement_ci_95_low"]:.2f}, {row["agreement_ci_95_high"]:.2f}] | '
            f'{row["cohen_kappa"]:.3f} '
            f'[{row["kappa_ci_95_low"]:.3f}, {row["kappa_ci_95_high"]:.3f}] | '
            f'{row["assignment_disagreement_triplets"]} | '
            f'{row["either_low_confidence_triplets"]} | '
            f'{row["either_indistinguishable_triplets"]} | '
            f'{row["adjudicated_triplets"]} |'
        )
    overall = reliability["ALL"]
    lines.extend([
        "",
        "总体上，A/B 在 51/100 个三元组上给出相同完整排列，Cohen's kappa 为 "
        f'{overall["cohen_kappa"]:.4f}（95% CI '
        f'{overall["kappa_ci_95_low"]:.3f}–{overall["kappa_ci_95_high"]:.3f}）。'
        f'共有 {overall["assignment_disagreement_triplets"]} 个排列分歧，'
        f'{overall["either_low_confidence_triplets"]} 个三元组被至少一名评分者标为低置信，'
        f'{overall["either_indistinguishable_triplets"]} 个被至少一名评分者标为不可区分；'
        f'最终 {overall["adjudicated_triplets"]}/100 个三元组按照预定程序进入裁决。',
        "",
        "## 4. 可复现性记录",
        "",
        f'- 原始 A/B 评分：`{blind_scores_path.name}`，SHA-256 `{_sha256(blind_scores_path)}`。',
        f'- 最终三元组判定：`{final_decisions_path.name}`，SHA-256 `{_sha256(final_decisions_path)}`。',
        "- CSV 使用 UTF-8 BOM，便于使用 Excel 复核。",
        "",
    ])
    return "\n".join(lines)


def run_analysis(
    blind_scores_path: Path,
    final_decisions_path: Path,
    output_dir: Path,
    *,
    bootstrap_samples: int = 10_000,
    seed: int = 20260802,
) -> dict[str, Path]:
    def portable_input_path(path: Path) -> str:
        parts = path.parts
        return Path(*parts[parts.index("data"):]).as_posix() if "data" in parts else path.name

    blind_rows = _read_csv(blind_scores_path)
    final_rows = _read_csv(final_decisions_path)
    metric_rows = analyze_metric_uncertainty(
        final_rows, bootstrap_samples=bootstrap_samples, seed=seed
    )
    reliability_rows = analyze_rater_reliability(
        blind_rows,
        final_rows,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "metrics_csv": output_dir / "formal_phase_a_metric_uncertainty.csv",
        "reliability_csv": output_dir / "formal_phase_a_rater_reliability.csv",
        "summary_json": output_dir / "formal_phase_a_statistical_analysis.json",
        "report_md": output_dir / "正式阶段A一致性与统计不确定性分析_2026-08-02.md",
    }
    rounded_metrics = _rounded(metric_rows)
    rounded_reliability = _rounded(reliability_rows)
    _write_csv(paths["metrics_csv"], rounded_metrics)
    _write_csv(paths["reliability_csv"], rounded_reliability)
    paths["summary_json"].write_text(
        json.dumps(
            {
                "analysis_unit": "triplet",
                "confidence_level": 0.95,
                "bootstrap_samples": bootstrap_samples,
                "random_seed": seed,
                "external_llm_api_calls": 0,
                "inputs": {
                    "blind_scores": {
                        "path": portable_input_path(blind_scores_path),
                        "sha256": _sha256(blind_scores_path),
                    },
                    "final_decisions": {
                        "path": portable_input_path(final_decisions_path),
                        "sha256": _sha256(final_decisions_path),
                    },
                },
                "metric_uncertainty": rounded_metrics,
                "rater_reliability": rounded_reliability,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    paths["report_md"].write_text(
        render_markdown(
            metric_rows,
            reliability_rows,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
            blind_scores_path=blind_scores_path,
            final_decisions_path=final_decisions_path,
        ),
        encoding="utf-8",
    )
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze E1 Phase-A uncertainty and inter-rater reliability."
    )
    parser.add_argument("--blind-scores", type=Path, required=True)
    parser.add_argument("--final-decisions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260802)
    args = parser.parse_args()
    paths = run_analysis(
        args.blind_scores,
        args.final_decisions,
        args.output_dir,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    print(json.dumps({key: str(path) for key, path in paths.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
