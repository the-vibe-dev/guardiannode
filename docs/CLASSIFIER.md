# Text Classifier

Two stages: deterministic rules first, then local LLM via Ollama. Merged into a final `RiskResult`.

## Rules engine

Patterns: off-platform contact, secrecy/coercion, age/location/school questions, private-info requests, Robux/gift-card scams, suspicious shorteners, bullying/threats, self-harm phrases, sexualized requests.

Each rule has severity, category label, confidence. Rules versioned in `backend/app/services/risk_rules.py`.

## LLM classifier

Prompt: `backend/app/prompts/text_classifier.txt`. Returns strict JSON:

```json
{
  "risk_level": "none|low|medium|high|critical",
  "score": 0,
  "categories": ["grooming", ...],
  "summary": "...",
  "evidence": ["..."],
  "recommended_action": "none|log|alert_parent|pause_app|block_app|emergency_review",
  "confidence": 0.0,
  "false_positive_notes": ""
}
```

Invalid JSON triggers one retry with a correction prompt.

## Merge

```
rules_score = max(matched rule severities)
llm_score   = parsed score
final_score = weighted_average(rules_score, llm_score)
final_level = max severity level from either
```

Rules engine has higher weight for the critical tier so high-confidence pattern matches aren't softened by LLM uncertainty.

## Age-group sensitivity

The child's age group goes into the prompt context. Stricter thresholds for younger children.

## Versioning

Each run records `prompt_version`, `rules_version`, `model` — supports reproducing historical alerts.

## Adding rules

PRs to `backend/app/services/risk_rules.py`. Each rule needs tests in `backend/tests/test_classifier.py` for both matches and false-positive borderlines.
