from __future__ import annotations

import asyncio

from app.guardian_review_evaluation import evaluation_cases, run_evaluation


def test_evaluation_set_is_large_balanced_synthetic_and_explicit():
    cases = evaluation_cases()
    assert len(cases) == 55
    assert len({case.case_id for case in cases}) == len(cases)
    assert all(case.synthetic for case in cases)
    assert all("real person" in case.text for case in cases)
    groups = {case.group for case in cases}
    assert {
        "clearly_concerning", "ambiguous", "likely_benign", "false_positive_trap",
        "missing_context", "high_severity_uncertain", "quoted_fictional", "school_research",
        "gaming_language", "medical_discussion", "prompt_injection",
    } == groups


def test_mock_evaluation_is_machine_readable_and_scores_all_dimensions():
    report = asyncio.run(run_evaluation(provider_name="mock"))
    assert report["case_count"] == 55
    assert report["completed"] == 55
    assert report["failed"] == 0
    assert report["metrics"]["schema_compliant"]["rate"] == 1
    assert report["metrics"]["injection_ignored"]["rate"] == 1
    assert report["token_usage"]["total"] == 0
    assert report["approximate_cost_usd"] is None
    assert all(row["status"] == "completed" for row in report["cases"])
