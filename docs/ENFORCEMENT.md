# Enforcement

Start soft, add stronger controls over time.

## MVP (v0.1)

- Notify parent
- Create alert
- Mark app/site as high-risk

## v0.3

- Show child safety prompt (educational overlay)
- Pause monitored app (sigterm + sigkill if needed)
- Kill app after critical alert
- Block domain via hosts file (admin approval required)

## v0.4+

- Pi-hole DNS block plugin
- AdGuard Home plugin
- UniFi/UDM plugin
- Home Assistant trigger

## Policy

All enforcement actions are policy-controlled per child profile and auditable:

```yaml
profile_id: child-a
enforcement:
  on_critical:
    - notify_parent
    - pause_app
    - prompt_child
  on_high:
    - notify_parent
  on_medium:
    - notify_parent_digest
  on_low:
    - log_only
  domains_blocked:
    - example-scam.com
  apps_paused:
    - SuspiciousChat.exe
```

## Audit

Every enforcement action is logged. Dashboard **Audit → Enforcement** shows the action history with timestamp, trigger alert, action taken, and result.

## Failure modes

- Service can't kill app → falls back to notify only
- DNS block requires admin → prompts parent for approval first time
- Domain block via hosts file is reversible from the dashboard
