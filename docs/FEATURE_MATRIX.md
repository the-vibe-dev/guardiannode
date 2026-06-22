# Feature Matrix

Status definitions:

- **Implemented**: shipped in source and covered by a named test or smoke check.
- **Experimental**: present but limited, operator-focused, or not fully qualified.
- **Planned**: documented design direction; not shipped as a usable feature.

| Feature | Status | Platform | Source module | Test reference |
|---|---|---|---|---|
| Parent dashboard | Implemented | Backend/web | `dashboard/src/App.tsx` | `dashboard/src/components/Layout.test.tsx` |
| Backend API and dashboard bundle | Implemented | Linux/Windows | `backend/app/main.py` | `backend/tests/test_readiness_apis.py` |
| Device pairing by six-digit code | Implemented | Backend/agent | `backend/app/services/pairing.py` | `backend/tests/test_device_auth.py` |
| Local all-in-one bootstrap pairing | Experimental | Backend/Windows installer | `backend/app/api/devices.py` | `backend/tests/test_pairing_local_bootstrap.py` |
| Child profiles and watch phrases | Implemented | Backend/web | `backend/app/services/profile_resolution.py` | `backend/tests/test_profile_resolution.py` |
| Screenshot upload and async classification | Implemented | Backend/agent | `backend/app/services/screenshot_async.py` | `backend/tests/test_image_mime.py` |
| Text event ingest | Implemented | Backend/agent | `backend/app/services/event_ingest.py` | `backend/tests/test_readiness_apis.py` |
| PNG/JPEG evidence MIME tracking | Implemented | Backend | `backend/app/api/events.py` | `backend/tests/test_image_mime.py` |
| Encrypted retained evidence | Implemented | Backend | `backend/app/services/encryption.py` | `backend/tests/test_export.py` |
| Export list/download/delete | Implemented | Backend/web | `backend/app/api/storage.py` | `backend/tests/test_export.py` |
| SMTP and webhook notification settings | Implemented | Backend/web | `backend/app/api/settings.py` | `backend/tests/test_readiness_apis.py` |
| mDNS discovery hints | Experimental | Backend/agent | `backend/app/services/mdns_advertiser.py` | `agent-windows/tests/test_pairing_bootstrap.py` |
| Windows tray/status UI | Experimental | Windows | `agent-windows/src/tray_app.py` | Manual Windows validation |
| Windows watchdog | Experimental | Windows | `agent-windows/src/watchdog.py` | `agent-windows/tests/test_watchdog.py` |
| Durable encrypted agent queue | Experimental | Windows | `agent-windows/src/durable_queue.py` | `agent-windows/tests/test_durable_queue.py` |
| Privileged Windows broker | Experimental | Windows | `agent-windows/src/broker_service.py` | `agent-windows/tests/test_broker_service.py` |
| Clipboard collector | Planned | Windows | Planned collector | Not implemented |
| File collector | Planned | Windows | Planned collector | Not implemented |
| Accessibility collector | Planned | Windows | Planned collector | Not implemented |
| Dedicated QR decoder | Planned | Backend/agent | Planned decoder | Not implemented |
| Built-in TLS/mTLS separated mode | Planned | Backend/agent | Planned transport layer | Not implemented |
