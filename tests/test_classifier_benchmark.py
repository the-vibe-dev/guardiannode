from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_classifier_benchmark.py"


def _module():
    spec = importlib.util.spec_from_file_location("classifier_benchmark", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rules_classifier_meets_versioned_beta_gates():
    module = _module()
    version, cases = module.load_cases(module.DEFAULT_CORPUS)
    assert version == "beta-1"
    assert len(cases) >= 150
    metrics = __import__("asyncio").run(module.run_benchmark(cases, "rules"))
    gates = __import__("json").loads(module.DEFAULT_GATES.read_text(encoding="utf-8"))[
        "rules"
    ]
    assert module.gate_failures(metrics, gates) == [], metrics
