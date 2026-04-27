"""Statistical analysis for evaluation results.

Computes median [IQR], paired Wilcoxon signed-rank tests with
Benjamini-Hochberg FDR correction, and generates result tables.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median

from lacquertutor.eval.metrics import TaskMetrics


def compute_summary(
    results: list[TaskMetrics], conditions: list[str]
) -> dict[str, dict[str, dict]]:
    """Compute per-condition summary statistics.

    Returns: {condition: {metric: {median, q1, q3, iqr, mean, n}}}
    """
    metric_names = [
        "m1_gate_compliance",
        "m2_missing_slot_errors",
        "m3a_checkpoint_coverage",
        "m3b_contingency_coverage",
        "m4a_evidence_coverage",
        "m4b_ungrounded_decisions",
        "m5_consistency_flags",
        "m6_questions_asked",
        "m6_slots_filled",
    ]

    summary: dict[str, dict[str, dict]] = {}

    for cond in conditions:
        cond_results = [r for r in results if r.condition == cond]
        if not cond_results:
            continue

        cond_summary: dict[str, dict] = {}
        for metric in metric_names:
            values = [getattr(r, metric) for r in cond_results]
            values_sorted = sorted(values)
            n = len(values_sorted)

            q1_idx = n // 4
            q3_idx = 3 * n // 4

            cond_summary[metric] = {
                "median": median(values_sorted),
                "q1": values_sorted[q1_idx] if n > 0 else 0,
                "q3": values_sorted[q3_idx] if n > 0 else 0,
                "mean": sum(values) / n if n > 0 else 0,
                "n": n,
            }

        summary[cond] = cond_summary

    return summary


def paired_wilcoxon(
    results: list[TaskMetrics],
    cond_a: str,
    cond_b: str,
    metric: str,
) -> dict[str, float]:
    """Compute paired Wilcoxon signed-rank test between two conditions.

    Returns: {statistic, p_value, effect_size_r}
    Requires scipy.
    """
    try:
        from scipy.stats import wilcoxon
    except ImportError:
        return {"error": "scipy not installed — run pip install scipy"}

    results_a = {r.task_id: r for r in results if r.condition == cond_a}
    results_b = {r.task_id: r for r in results if r.condition == cond_b}

    # Paired: only tasks present in both conditions
    common_tasks = sorted(set(results_a.keys()) & set(results_b.keys()))
    if len(common_tasks) < 5:
        return {"error": f"Too few paired observations: {len(common_tasks)}"}

    values_a = [getattr(results_a[t], metric) for t in common_tasks]
    values_b = [getattr(results_b[t], metric) for t in common_tasks]

    # Check if all differences are zero
    diffs = [a - b for a, b in zip(values_a, values_b)]
    if all(d == 0 for d in diffs):
        return {"statistic": 0, "p_value": 1.0, "effect_size_r": 0.0, "n": len(common_tasks)}

    stat, p = wilcoxon(values_a, values_b)
    n = len(common_tasks)
    # Rank-biserial correlation as effect size
    r = 1 - (2 * stat) / (n * (n + 1) / 2) if n > 0 else 0

    return {
        "statistic": float(stat),
        "p_value": float(p),
        "effect_size_r": float(r),
        "n": n,
    }


def benjamini_hochberg(p_values: list[float], q: float = 0.05) -> list[float]:
    """Apply Benjamini-Hochberg FDR correction to a list of p-values.

    Returns adjusted p-values.
    """
    n = len(p_values)
    if n == 0:
        return []

    # Sort p-values with indices
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])

    adjusted = [0.0] * n
    for rank, (orig_idx, p) in enumerate(indexed, 1):
        adjusted[orig_idx] = min(p * n / rank, 1.0)

    # Enforce monotonicity (step-down)
    for i in range(n - 2, -1, -1):
        sorted_idx = indexed[i][0]
        next_sorted_idx = indexed[i + 1][0]
        adjusted[sorted_idx] = min(adjusted[sorted_idx], adjusted[next_sorted_idx])

    return adjusted


def generate_result_table_markdown(
    summary: dict[str, dict[str, dict]],
    conditions: list[str],
) -> str:
    """Generate a Markdown table matching the paper's Table 8 format."""
    lines = [
        "| Metric | " + " | ".join(conditions) + " |",
        "|--------|" + "|".join(["--------"] * len(conditions)) + "|",
    ]

    metric_labels = {
        "m1_gate_compliance": "M1 Gate compliance ↑",
        "m2_missing_slot_errors": "M2 Missing-slot errors ↓",
        "m3a_checkpoint_coverage": "M3a Checkpoint coverage ↑",
        "m3b_contingency_coverage": "M3b Contingency coverage ↑",
        "m4a_evidence_coverage": "M4a Evidence coverage ↑",
        "m4b_ungrounded_decisions": "M4b Ungrounded decisions ↓",
        "m5_consistency_flags": "M5 Consistency flags ↓",
        "m6_questions_asked": "M6 Questions asked",
        "m6_slots_filled": "M6 Slots filled",
    }

    for metric, label in metric_labels.items():
        row = f"| {label} |"
        for cond in conditions:
            if cond in summary and metric in summary[cond]:
                s = summary[cond][metric]
                med = s["median"]
                q1 = s["q1"]
                q3 = s["q3"]
                if isinstance(med, float):
                    row += f" {med:.2f} [{q1:.2f}, {q3:.2f}] |"
                else:
                    row += f" {med} [{q1}, {q3}] |"
            else:
                row += " — |"
        lines.append(row)

    return "\n".join(lines)
