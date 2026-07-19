"""Mock, Codex OAuth, and direct Responses API providers."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.guardian_review_models import GuardianReviewAssessment, ModelUsage, strict_output_schema

_CATEGORIES = {
    "none", "self_harm", "grooming", "sexual_content", "sexual_exploitation",
    "child_sexual_content", "nudity", "bullying", "threat", "scam", "phishing",
    "private_info", "private_info_request", "private_info_visible", "off_platform_contact",
    "secrecy_request", "drugs", "weapons", "gore", "hate_symbol", "dangerous_challenge",
    "profanity", "unknown_link", "custom_watch", "monitoring_gap", "unknown",
}


class ProviderError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False, retry_after: float | None = None):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after


@dataclass(frozen=True)
class ProviderResult:
    assessment: GuardianReviewAssessment
    model_returned: str | None
    response_id: str | None
    latency_ms: int
    usage: ModelUsage | None = None


def _mock_assessment(payload: dict[str, Any]) -> GuardianReviewAssessment:
    findings = payload.get("local_detector_findings") or {}
    severity = findings.get("severity") if findings.get("severity") in {"none", "low", "medium", "high", "critical"} else "medium"
    categories = findings.get("categories") or []
    category = categories[0] if categories and categories[0] in _CATEGORIES else "unknown"
    evidence = payload.get("minimized_evidence") or []
    immediate_danger = bool(payload.get("parent_believes_immediate_danger"))
    repeated = payload.get("behavior_repeated", "unknown")
    age_group = payload.get("approximate_child_age_group") or "unknown"
    relationship = payload.get("known_relationship_context", "unknown")
    goal = payload.get("parent_goal", "understand_context")
    assessment = (
        "concerning" if severity in {"high", "critical"}
        else "likely_benign" if severity in {"none", "low"}
        else "ambiguous"
    )
    tone = "safety_first" if immediate_danger else "urgent_and_reassuring" if severity == "critical" else "calm_and_curious"
    age_wording = {
        "under_10": "Use short, concrete questions and reassure them they are not in trouble.",
        "10_13": "Use simple, open questions and allow time for an answer.",
        "14_17": "Respect growing independence while being direct about safety.",
        "unknown": "Adjust the wording to the child's maturity and communication style.",
    }[age_group]
    pattern_wording = "Because this appears repeated, ask about the pattern without assuming motive." if repeated == "yes" else "First establish whether this was isolated or part of a pattern."
    relationship_wording = f"The supplied relationship context is {str(relationship).replace('_', ' ')}; confirm that context before drawing conclusions."
    return GuardianReviewAssessment.model_validate({
        "schema_version": "1.1.0",
        "assessment": assessment,
        "category": category,
        "severity": severity,
        "confidence": 0.72,
        "plain_language_summary": "The local findings merit a calm, context-seeking conversation; this synthetic assessment does not establish intent.",
        "observed_facts": [str(findings.get("summary") or "A local detector created an incident.")[:1000]],
        "inferences": ["The available signals may indicate a safety concern, but context is incomplete."],
        "supporting_evidence": [
            {"evidence_id": str(item.get("evidence_id", "unknown")), "observation": "A minimized excerpt was selected by the parent.", "relevance": "It contributed to the local detector finding."}
            for item in evidence[:3]
        ],
        "possible_benign_explanations": ["The content may be quoted, fictional, educational, or missing surrounding context."],
        "missing_context": ["Who was involved and what happened before and after the captured material."],
        "questions_parent_should_answer": [pattern_wording, relationship_wording],
        "recommended_parent_tone": {"tone": tone, "rationale": "A non-accusatory opening makes it easier to learn missing context while separating immediate safety from later consequences."},
        "suggested_opening_language": "I noticed something that raised a question for me. You are not in trouble based on this alert. Can you help me understand what was happening?",
        "questions_to_ask_child": ["What was happening here?", "How did this interaction make you feel?", age_wording],
        "phrases_or_approaches_to_avoid": ["Avoid claiming you already know another person's intent."],
        "immediate_actions": [{"priority": "today", "action": "Review the original local evidence and talk calmly with the child.", "rationale": "The assessment is limited to minimized context."}],
        "follow_up_actions": [{"timeframe": "within_one_week", "action": f"Follow up in a way that supports the parent's goal to {str(goal).replace('_', ' ')}.", "rationale": "Patterns and added context can change the appropriate response."}],
        "escalation_indicators": ["A credible statement of imminent harm, coercion, or inability to remain safe."],
        "limitations": ["This is a deterministic synthetic result for development and is not a live model assessment."],
    })


class MockProvider:
    async def assess(self, *, payload: dict[str, Any], prompt: str, model: str, timeout: float) -> ProviderResult:
        del prompt, timeout
        started = time.monotonic()
        assessment = _mock_assessment(payload)
        return ProviderResult(
            assessment,
            f"mock:{model}",
            "mock-response",
            int((time.monotonic() - started) * 1000),
            ModelUsage(input_tokens=0, cached_input_tokens=0, output_tokens=0, reasoning_tokens=0, total_tokens=0),
        )


class OpenAIResponsesProvider:
    def __init__(self, *, api_key: str | None, base_url: str, client: httpx.AsyncClient | None = None):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = client

    async def assess(self, *, payload: dict[str, Any], prompt: str, model: str, timeout: float) -> ProviderResult:
        if not self.api_key:
            raise ProviderError("provider_auth_required")
        body = {
            "model": model,
            "store": False,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": "INCIDENT_DATA\n" + json.dumps(payload, sort_keys=True)}]},
            ],
            "text": {"format": {"type": "json_schema", "name": "guardian_review_assessment", "strict": True, "schema": strict_output_schema()}},
            "reasoning": {"effort": "medium"},
            "max_output_tokens": 5000,
            "tools": [],
        }
        started = time.monotonic()
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=httpx.Timeout(timeout))
        try:
            response = await client.post(
                f"{self.base_url}/responses",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=timeout,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ProviderError("upstream_timeout" if isinstance(exc, httpx.TimeoutException) else "upstream_unavailable", retryable=True) from None
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code >= 400:
            retry_after = _retry_after(response.headers.get("retry-after"))
            error_type = ""
            try:
                error_type = str((response.json().get("error") or {}).get("type") or "")
            except Exception:
                pass
            if response.status_code in {408, 500, 502, 503, 504}:
                raise ProviderError("upstream_unavailable", retryable=True, retry_after=retry_after)
            if response.status_code == 429 and error_type not in {"insufficient_quota", "billing_hard_limit_reached"}:
                raise ProviderError("rate_limited", retryable=True, retry_after=retry_after)
            if response.status_code in {401, 403}:
                raise ProviderError("provider_auth_required")
            if response.status_code in {400, 422}:
                raise ProviderError("upstream_policy_or_validation")
            raise ProviderError("upstream_unavailable")
        try:
            data = response.json()
            if data.get("status") == "incomplete":
                raise ProviderError("invalid_model_output")
            output_text = _response_output_text(data)
            assessment = GuardianReviewAssessment.model_validate_json(output_text)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError("invalid_model_output") from None
        return ProviderResult(
            assessment=assessment,
            model_returned=str(data.get("model")) if data.get("model") else None,
            response_id=str(data.get("id")) if data.get("id") else None,
            latency_ms=int((time.monotonic() - started) * 1000),
            usage=_usage(data.get("usage")),
        )


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _usage(value: Any) -> ModelUsage | None:
    if not isinstance(value, dict):
        return None
    input_details = value.get("input_tokens_details") or {}
    output_details = value.get("output_tokens_details") or {}
    usage = ModelUsage(
        input_tokens=_nonnegative_int(value.get("input_tokens")),
        cached_input_tokens=_nonnegative_int(input_details.get("cached_tokens")),
        output_tokens=_nonnegative_int(value.get("output_tokens")),
        reasoning_tokens=_nonnegative_int(output_details.get("reasoning_tokens")),
        total_tokens=_nonnegative_int(value.get("total_tokens")),
    )
    return usage if any(item is not None for item in usage.model_dump().values()) else None


def _response_output_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    for item in data.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "refusal":
                raise ProviderError("upstream_refusal")
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise ProviderError("invalid_model_output")


def _retry_after(value: str | None) -> float | None:
    try:
        return min(30.0, max(0.0, float(value))) if value is not None else None
    except ValueError:
        return None


class CodexProvider:
    def __init__(self, *, executable: str, codex_home: Path):
        self.executable = executable
        self.codex_home = codex_home

    async def assess(self, *, payload: dict[str, Any], prompt: str, model: str, timeout: float) -> ProviderResult:
        executable = shutil.which(self.executable) if not Path(self.executable).is_file() else self.executable
        if not executable:
            raise ProviderError("provider_unavailable")
        self.codex_home.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(self.codex_home, 0o700)
        env = os.environ.copy()
        env["CODEX_HOME"] = str(self.codex_home)
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="guardian-review-", dir=self.codex_home) as tmp:
            root = Path(tmp)
            schema_path = root / "schema.json"
            output_path = root / "assessment.json"
            schema_path.write_text(json.dumps(strict_output_schema()), encoding="utf-8")
            command = [
                str(executable), "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                "--sandbox", "read-only", "--skip-git-repo-check", "--model", model,
                "--output-schema", str(schema_path), "--output-last-message", str(output_path),
                "-c", 'approval_policy="never"', "-",
            ]
            process_options: dict[str, Any] = {}
            if os.name == "nt":
                process_options["creationflags"] = 0x00000200  # CREATE_NEW_PROCESS_GROUP
            else:
                process_options["start_new_session"] = True
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=root,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **process_options,
            )
            request_text = prompt + "\n\nINCIDENT_DATA\n" + json.dumps(payload, sort_keys=True)
            try:
                console_output = await asyncio.wait_for(process.communicate(request_text.encode("utf-8")), timeout=timeout)
            except TimeoutError:
                await _terminate_process_tree(process)
                raise ProviderError("upstream_timeout", retryable=True) from None
            if process.returncode != 0 or not output_path.exists():
                raise _codex_failure(console_output)
            try:
                assessment = GuardianReviewAssessment.model_validate_json(output_path.read_text("utf-8"))
            except Exception:
                raise ProviderError("invalid_model_output") from None
        return ProviderResult(assessment, model, None, int((time.monotonic() - started) * 1000))


async def _terminate_process_tree(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    if os.name == "nt":
        killer = await asyncio.create_subprocess_exec(
            "taskkill", "/PID", str(process.pid), "/T", "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await killer.wait()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    await process.wait()


def _codex_failure(console_output: tuple[bytes | None, bytes | None]) -> ProviderError:
    # Inspect in memory only. Console output can echo the prompt and must never
    # be logged, persisted, returned, or included in an exception message.
    combined = b" ".join(part or b"" for part in console_output).decode("utf-8", errors="ignore").lower()
    if any(marker in combined for marker in ("not logged in", "unauthorized", '"status":401', '"status":403')):
        return ProviderError("provider_auth_required")
    if any(marker in combined for marker in ("not supported", "invalid_request_error", "policy_violation")):
        return ProviderError("upstream_policy_or_validation")
    if "rate limit" in combined or '"status":429' in combined:
        return ProviderError("rate_limited", retryable=True)
    return ProviderError("provider_unavailable", retryable=True)


def provider_for(settings, *, provider_name: str | None = None, client: httpx.AsyncClient | None = None):
    provider = (provider_name or settings.guardian_review_provider).strip().lower()
    if provider == "mock":
        return MockProvider()
    if provider == "openai":
        if not settings.guardian_review_zdr_confirmed:
            raise ProviderError("zdr_not_confirmed")
        return OpenAIResponsesProvider(api_key=settings.openai_api_key or os.getenv("OPENAI_API_KEY"), base_url=settings.guardian_review_openai_base_url, client=client)
    if provider == "codex":
        # A coding-agent session can have local read tools and inherits process
        # credentials. Incident evidence must not enter that capability boundary.
        # Re-enable only when the transport provides an enforceable zero-tool,
        # minimal-environment contract equivalent to the Responses API path.
        raise ProviderError("provider_unavailable")
    raise ProviderError("configuration_error")
