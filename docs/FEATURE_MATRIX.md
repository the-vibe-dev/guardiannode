# Feature Matrix

The columns intentionally separate implementation from release qualification.
`Qualified` means the exact named build passed its platform gate. This changed
review.3 source is an alpha/developer preview. Prior-build Windows, Docker and
browser results do not qualify it. Current evidence is in the included report.

Screenshot capture and AI review are the product scope. Screen-time limits,
website/app blocking and exception approvals are retired, not planned gaps.

| Feature | Code | Automated coverage | Platform qualification | Field validation | Release status | Source module | Test reference |
|---|---|---|---|---|---|---|---|
| Parent dashboard | Present | Source tests; platform gate pending | Current build unqualified | Not established for this build | Alpha / developer preview | `dashboard/src/App.tsx` | `dashboard/e2e/family-dashboard.spec.ts` |
| Backend API and dashboard bundle | Present | Integration | Current build unqualified | Not established for this build | Alpha / developer preview | `backend/app/main.py` | `backend/tests/test_readiness_apis.py` |
| Family-CA HTTPS pairing | Present | Integration | Source checks only | Not established for this build | Alpha / developer preview | `agent-windows/src/pairing_client.py` | `agent-windows/tests/test_pairing_bootstrap.py` |
| Local all-in-one bootstrap | Present | Integration | Source checks only | Not established for this build | Alpha / developer preview | `backend/app/api/devices.py` | `backend/tests/test_pairing_local_bootstrap.py` |
| Screenshot upload and classification | Present | Integration | Source checks only | Not established for this build | Alpha / developer preview | `backend/app/services/screenshot_async.py` | `backend/tests/test_image_mime.py` |
| Server-side OCR | Present | Source tests; platform gate pending | Source checks only | Not established for this build | Alpha / developer preview | `backend/app/services/ocr.py` | `scripts/docker_canary.py` |
| Deterministic rule classification | Present | Corpus gate | Source checks only | Not established for this build | Alpha / developer preview | `backend/app/services/risk_rules.py` | `tests/test_classifier_benchmark.py` |
| Local Ollama classification | Present | Mock integration | Source checks only | Not established for this build | Alpha / developer preview | `backend/app/services/classifier.py` | `backend/tests/test_model_fallback.py` |
| Encrypted retained evidence | Present | Integration | Source checks only | Not established for this build | Alpha / developer preview | `backend/app/services/encryption.py` | `backend/tests/test_export.py` |
| Export list/download/delete | Present | Integration | Source checks only | Not established for this build | Alpha / developer preview | `backend/app/api/storage.py` | `backend/tests/test_export.py` |
| Portable `.gna` archive and clean-host restore | Present | Integration | Source checks only | Not established for this build | Alpha / developer preview | `backend/app/archive/format.py` | `backend/tests/test_archive_format.py` |
| Complete scheduled recovery backup | Present | Integration | Source checks only | Not established for this build | Alpha / developer preview | `backend/app/workers/backup_worker.py` | `backend/tests/test_migrations_and_readiness.py` |
| Administrative step-up authentication | Present | Integration | Source checks only | Not established for this build | Alpha / developer preview | `backend/app/api/deps.py` | `backend/tests/test_session_security.py` |
| Windows tray/status UI | Present | Partial unit | Current build unqualified | Not established for this build | Alpha / developer preview | `agent-windows/src/tray_app.py` | Manual Windows validation |
| Windows watchdog | Present | Unit | Current build unqualified | Not established for this build | Alpha / developer preview | `agent-windows/src/watchdog.py` | `agent-windows/tests/test_watchdog.py` |
| Durable encrypted agent queue | Present | Unit | Source checks only | Not established for this build | Alpha / developer preview | `agent-windows/src/durable_queue.py` | `agent-windows/tests/test_durable_queue.py` |
| Privileged Windows broker | Present | Unit | Current build unqualified | Not established for this build | Alpha / developer preview | `agent-windows/src/broker_service.py` | `agent-windows/tests/test_broker_service.py` |
| Legacy restriction release only | Present | Unit + integration | Source checks only | Not established for this build | Recovery compatibility | `agent-windows/src/legacy_recovery.py` | `agent-windows/tests/test_legacy_recovery.py` |
| Explicit consent and withdrawal | Present | Source tests; platform gate pending | Source checks only | Not established for this build | Alpha / developer preview | `backend/app/api/consent.py` | `backend/tests/test_readiness_apis.py` |
| Metadata-only daily digest | Present | Unit | Source checks only | Not established for this build | Alpha / developer preview | `backend/app/services/daily_digest.py` | `backend/tests/test_daily_digest.py` |
| Docker Compose deployment | Present | Source tests; platform gate pending | Current build unqualified | Not established for this build | Alpha / developer preview | `installer/server-linux/docker-compose.yml` | `scripts/docker_canary.py` |
| Built-in server-authenticated TLS | Present | Unit + integration | Source checks only | Not established for this build | Alpha / developer preview | `backend/app/services/local_tls.py` | `backend/tests/test_local_tls.py` |
| Mutual TLS/device certificates | Absent | None | Not qualified | None | Planned | Planned transport layer | Not implemented |
| Automatic application updates | Absent | None | Not qualified | None | Planned | Planned updater | Not implemented |

See [Closed Beta Release Gates](RELEASE_GATES.md) for promotion requirements and
[Version Support Policy](VERSION_SUPPORT.md) for the qualified runtime baseline.
