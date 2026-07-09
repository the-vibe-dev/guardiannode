#!/usr/bin/env python3
"""Run the versioned text-safety benchmark and enforce beta quality gates."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from statistics import quantiles
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services import risk_rules  # noqa: E402

DEFAULT_CORPUS = ROOT / "tests" / "benchmarks" / "text_safety_scenarios.json"
DEFAULT_GATES = ROOT / "tests" / "benchmarks" / "quality_gates.json"


def load_cases(path: Path) -> tuple[str, list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expanded = []
    for case in payload["cases"]:
        for index, wrapper in enumerate(payload["context_wrappers"]):
            expanded.append(
                {
                    **case,
                    "id": f"{case['id']}@{index}",
                    "text": wrapper.format(text=case["text"]),
                }
            )
    return str(payload["version"]), expanded


async def _classify(case: dict[str, Any], mode: str) -> tuple[str, set[str]]:
    if mode == "rules":
        matches = risk_rules.evaluate(case["text"])
        return risk_rules.max_severity(matches), set(
            risk_rules.aggregated_categories(matches)
        )
    from app.services import classifier

    result = await classifier.classify_text(redacted_text=case["text"], use_llm=True)
    return str(result["risk_level"]), set(result["categories"])


async def run_benchmark(cases: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    critical_total = critical_hit = category_total = category_hit = 0
    latencies: list[float] = []
    failures: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        severity, categories = await _classify(case, mode)
        latencies.append((time.perf_counter() - started) * 1000)
        predicted = severity != "none"
        expected = bool(case["positive"])
        if expected and predicted:
            tp += 1
        elif expected:
            fn += 1
        elif predicted:
            fp += 1
        else:
            tn += 1
        if case["severity"] == "critical":
            critical_total += 1
            critical_hit += int(severity == "critical")
        expected_categories = set(case["categories"])
        category_total += len(expected_categories)
        category_hit += len(expected_categories & categories)
        if (
            expected != predicted
            or not expected_categories.issubset(categories)
            or (case["severity"] == "critical" and severity != "critical")
        ):
            failures.append(
                {
                    "id": case["id"],
                    "expected_severity": case["severity"],
                    "actual_severity": severity,
                    "missing_categories": sorted(expected_categories - categories),
                }
            )

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    p95 = (
        quantiles(latencies, n=100, method="inclusive")[94]
        if len(latencies) > 1
        else latencies[0]
    )
    return {
        "cases": len(cases),
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "critical_recall": critical_hit / critical_total if critical_total else 1.0,
        "category_recall": category_hit / category_total if category_total else 1.0,
        "p95_latency_ms": p95,
        "failures": failures[:25],
    }


def gate_failures(metrics: dict[str, Any], gates: dict[str, Any]) -> list[str]:
    comparisons = (
        ("cases", "minimum_cases", lambda actual, target: actual >= target),
        ("precision", "minimum_precision", lambda actual, target: actual >= target),
        ("recall", "minimum_recall", lambda actual, target: actual >= target),
        (
            "critical_recall",
            "minimum_critical_recall",
            lambda actual, target: actual >= target,
        ),
        (
            "category_recall",
            "minimum_category_recall",
            lambda actual, target: actual >= target,
        ),
        (
            "p95_latency_ms",
            "maximum_p95_latency_ms",
            lambda actual, target: actual <= target,
        ),
    )
    return [
        f"{metric}={metrics[metric]:.4f} failed {gate}={gates[gate]}"
        for metric, gate, passes in comparisons
        if not passes(metrics[metric], gates[gate])
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("rules", "live"), default="rules")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--gates", type=Path, default=DEFAULT_GATES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    corpus_version, cases = load_cases(args.corpus)
    gate_payload = json.loads(args.gates.read_text(encoding="utf-8"))
    metrics = asyncio.run(run_benchmark(cases, args.mode))
    failures = gate_failures(metrics, gate_payload[args.mode])
    report = {
        "corpus_version": corpus_version,
        "gate_version": gate_payload["version"],
        "mode": args.mode,
        "passed": not failures,
        "gate_failures": failures,
        "metrics": metrics,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
