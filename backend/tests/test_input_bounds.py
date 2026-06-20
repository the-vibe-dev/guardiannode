from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.services import pipeline_metrics, rate_limit
from app.services.input_bounds import InputBoundsError, sanitize_metadata


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("GUARDIANNODE_DATA_DIR", str(tmp_path))
    from app import settings as settings_mod

    settings_mod.settings = settings_mod.Settings()
    settings_mod.settings.mdns_enabled = False
    rate_limit._clear_all()
    pipeline_metrics.reset_for_tests()

    from app.db.models import Base
    from app.db.session import get_engine
    from app.main import create_app

    Base.metadata.create_all(bind=get_engine())
    return TestClient(create_app(), client=("127.0.0.1", 50000))


def _paired_token(client: TestClient) -> str:
    from app.services.device_bootstrap_token import ensure_device_bootstrap_token

    response = client.post(
        "/api/devices/bootstrap-local",
        json={
            "hostname": "kid-pc",
            "platform": "windows",
            "agent_version": "0.1.0-alpha.1",
            "device_bootstrap_token": ensure_device_bootstrap_token(),
        },
    )
    assert response.status_code == 200
    return response.json()["device_token"]


def test_sanitize_metadata_rejects_non_json_primitives():
    with pytest.raises(InputBoundsError, match="finite"):
        sanitize_metadata({"score": math.inf})
    with pytest.raises(InputBoundsError, match="JSON primitive"):
        sanitize_metadata({"bad": object()})


def test_sanitize_metadata_bounds_shape_and_size():
    with pytest.raises(InputBoundsError, match="too many entries"):
        sanitize_metadata({f"k{i}": i for i in range(101)})
    with pytest.raises(InputBoundsError, match="deeply nested"):
        sanitize_metadata({"a": {"b": {"c": {"d": {"e": "too deep"}}}}})
    with pytest.raises(InputBoundsError, match="too long"):
        sanitize_metadata({"message": "x" * 2049})


def test_event_ingest_rejects_oversized_metadata(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    token = _paired_token(client)

    response = client.post(
        "/api/events",
        json={
            "source_type": "browser",
            "redacted_text": "ordinary text",
            "metadata": {"message": "x" * 2049},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
