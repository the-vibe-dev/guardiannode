# Feature Matrix

The columns intentionally separate implementation from release qualification.
`Qualified` means the named platform gate passed; it does not mean production
ready. GuardianNode currently makes no production-readiness claim.

| Feature | Code | Automated coverage | Platform qualification | Field validation | Release status | Source module | Test reference |
|---|---|---|---|---|---|---|---|
| Parent dashboard | Present | Unit | Web bundle tested | Limited | Beta candidate | `dashboard/src/App.tsx` | `dashboard/src/components/Layout.test.tsx` |
| Backend API and dashboard bundle | Present | Integration | Linux/Windows candidate | Limited | Beta candidate | `backend/app/main.py` | `backend/tests/test_readiness_apis.py` |
| Device pairing | Present | Integration | Windows candidate | Validated | Beta candidate | `backend/app/services/pairing.py` | `backend/tests/test_device_auth.py` |
| Local all-in-one bootstrap | Present | Integration | Windows candidate | Validated | Experimental | `backend/app/api/devices.py` | `backend/tests/test_pairing_local_bootstrap.py` |
| Screenshot upload and classification | Present | Integration | Windows candidate | Validated | Beta candidate | `backend/app/services/screenshot_async.py` | `backend/tests/test_image_mime.py` |
| Server-side OCR | Present | Clean-container canary | Docker qualified | Limited | Beta candidate | `backend/app/services/ocr.py` | `scripts/docker_canary.py` |
| Deterministic rule classification | Present | Corpus gate | Source qualified | Validated | Beta candidate | `backend/app/services/risk_rules.py` | `tests/test_classifier_benchmark.py` |
| Local Ollama classification | Present | Mock integration | Windows candidate | Validated | Experimental | `backend/app/services/classifier.py` | `backend/tests/test_model_fallback.py` |
| Encrypted retained evidence | Present | Integration | Source qualified | Limited | Beta candidate | `backend/app/services/encryption.py` | `backend/tests/test_export.py` |
| Export list/download/delete | Present | Integration | Source qualified | Limited | Beta candidate | `backend/app/api/storage.py` | `backend/tests/test_export.py` |
| Portable `.gna` archive and clean-host restore | Present | Integration | Source qualified | Limited | Beta candidate | `backend/app/archive/format.py` | `backend/tests/test_archive_format.py` |
| Complete scheduled recovery backup | Present | Integration | Source qualified | None | Experimental | `backend/app/workers/backup_worker.py` | `backend/tests/test_migrations_and_readiness.py` |
| Administrative step-up authentication | Present | Integration | Source qualified | None | Beta candidate | `backend/app/api/deps.py` | `backend/tests/test_session_security.py` |
| Windows tray/status UI | Present | Partial unit | Windows candidate | Validated | Experimental | `agent-windows/src/tray_app.py` | Manual Windows validation |
| Windows watchdog | Present | Unit | Windows candidate | Validated | Experimental | `agent-windows/src/watchdog.py` | `agent-windows/tests/test_watchdog.py` |
| Durable encrypted agent queue | Present | Unit | Windows candidate | Limited | Experimental | `agent-windows/src/durable_queue.py` | `agent-windows/tests/test_durable_queue.py` |
| Privileged Windows broker | Present | Unit | Windows candidate | Validated | Experimental | `agent-windows/src/broker_service.py` | `agent-windows/tests/test_broker_service.py` |
| Docker Compose deployment | Present | Clean OCR-to-alert canary | Linux CI qualified | CI validated | Closed-beta candidate | `installer/server-linux/docker-compose.yml` | `scripts/docker_canary.py` |
| Built-in TLS/mTLS separated mode | Absent | None | Not qualified | None | Planned | Planned transport layer | Not implemented |
| Automatic application updates | Absent | None | Not qualified | None | Planned | Planned updater | Not implemented |

See [Closed Beta Release Gates](RELEASE_GATES.md) for promotion requirements and
[Version Support Policy](VERSION_SUPPORT.md) for the qualified runtime baseline.
