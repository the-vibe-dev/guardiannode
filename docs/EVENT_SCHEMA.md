# Event Schema

The shared event format used between the agent and backend.

JSON Schema files live in `shared/schemas/`. Pydantic equivalents in `shared/python/schemas.py`.

## Event

```json
{
  "event_id": "01HXY...",
  "device_id": "child-laptop-01",
  "profile_id": "child-a",
  "source_type": "ocr",
  "app_name": "Roblox.exe",
  "window_title": "Roblox - PLS DONATE",
  "url": null,
  "timestamp": "2026-05-27T14:32:00-04:00",
  "redacted_text": "hey add me on discord and don't tell your parents",
  "evidence_type": "visible_text",
  "screenshot_blob_id": null,
  "metadata": {
    "ocr_confidence": 0.87,
    "foreground": true,
    "rules_version": "0.1.0-alpha.1",
    "agent_version": "0.1.0-alpha.1"
  }
}
```

`source_type` values are tracked by implementation status:

| Status | Values | Notes |
|---|---|---|
| Implemented | `ocr`, `image` | Text events and screenshot/image events are accepted by the backend today. |
| Experimental / integration-specific | `browser` | Supported by schema/API paths where a collector provides browser context. |
| Reserved | `clipboard`, `file`, `accessibility` | Reserved for future collectors; the Windows alpha agent does not ship these collection paths. |

## RiskResult

```json
{
  "risk_id": "01HXY...",
  "event_id": "01HXY...",
  "risk_level": "high",
  "score": 87,
  "categories": ["grooming", "off_platform_contact", "secrecy_request"],
  "summary": "Asked the child to move to Discord and keep it secret.",
  "evidence": ["asked to move to Discord", "told child not to tell parents"],
  "recommended_action": "alert_parent",
  "model": "llama3.2:3b",
  "rules_triggered": ["off_platform_contact", "secrecy_phrase"],
  "confidence": 0.84,
  "prompt_version": "abc1234",
  "rules_version": "0.1.0-alpha.1"
}
```

## Alert

```json
{
  "alert_id": "01HXY...",
  "risk_id": "01HXY...",
  "device_id": "child-laptop-01",
  "profile_id": "child-a",
  "severity": "high",
  "status": "open",
  "created_at": "2026-05-27T14:32:01-04:00",
  "reviewed_by": null,
  "reviewed_at": null,
  "action_taken": null
}
```

## Risk categories

`grooming`, `off_platform_contact`, `secrecy_request`, `bullying`, `harassment`, `self_harm`, `sexual_content`, `nudity`, `gore`, `weapons`, `drugs`, `hate_symbol`, `private_info_request`, `scam`, `phishing`, `threat`, `dangerous_challenge`, `violence`, `qr_code`, `phishing_screenshot`, `private_info_visible`.
