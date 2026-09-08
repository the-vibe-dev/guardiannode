"""HTTP client for the GuardianNode backend."""
from __future__ import annotations

from pathlib import Path

import httpx


class BackendClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 30.0,
        *,
        ca_path: str | Path | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.ca_path = str(ca_path) if ca_path else None

    def _verify(self) -> bool | str:
        if self.base_url.lower().startswith("https://"):
            if not self.ca_path:
                raise RuntimeError("HTTPS backend requires the enrolled GuardianNode family CA")
            return self.ca_path
        return True

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def health(self) -> dict:
        async with httpx.AsyncClient(timeout=5.0, verify=self._verify()) as c:
            r = await c.get(f"{self.base_url}/api/health")
            r.raise_for_status()
            return r.json()

    async def send_event(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout, verify=self._verify()) as c:
            r = await c.post(
                f"{self.base_url}/api/events", json=payload, headers=self._headers()
            )
            r.raise_for_status()
            return r.json()

    async def send_screenshot(
        self,
        *,
        image_bytes: bytes,
        app_name: str | None = None,
        window_title: str | None = None,
        url: str | None = None,
        profile_id: str | None = None,
        age_group: str = "10_13",
        capture_scope: str = "monitored_app",
        policy_id: str | None = None,
        policy_version: str | None = None,
        collector_version: str | None = None,
        timestamp: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        files = {"image": ("screen.jpg", image_bytes, "image/jpeg")}
        data: dict[str, str] = {"age_group": age_group, "capture_scope": capture_scope}
        if app_name:
            data["app_name"] = app_name
        if window_title:
            data["window_title"] = window_title
        if url:
            data["url"] = url
        if profile_id:
            data["profile_id"] = profile_id
        if policy_id:
            data["policy_id"] = policy_id
        if policy_version:
            data["policy_version"] = policy_version
        if collector_version:
            data["collector_version"] = collector_version
        if timestamp:
            data["timestamp"] = timestamp
        if idempotency_key:
            data["idempotency_key"] = idempotency_key
        async with httpx.AsyncClient(timeout=max(self.timeout, 120.0), verify=self._verify()) as c:
            r = await c.post(
                f"{self.base_url}/api/events/screenshot",
                files=files,
                data=data,
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def heartbeat(self, queued_frames: int = 0) -> bool:
        """Liveness + upload-backlog report. Falls back to the plain health
        probe when talking to a backend that predates /api/devices/heartbeat."""
        try:
            async with httpx.AsyncClient(timeout=5.0, verify=self._verify()) as c:
                r = await c.post(
                    f"{self.base_url}/api/devices/heartbeat",
                    headers=self._headers(),
                    json={"queued_frames": queued_frames},
                )
                if r.status_code in (404, 405):
                    r = await c.get(f"{self.base_url}/api/health", headers=self._headers())
                return r.status_code == 200
        except Exception:
            return False

    async def get_capture_config(self) -> dict | None:
        """Fetch capture settings the parent set via the child's policy."""
        try:
            async with httpx.AsyncClient(timeout=5.0, verify=self._verify()) as c:
                r = await c.get(
                    f"{self.base_url}/api/devices/capture-config",
                    headers=self._headers(),
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            pass
        return None

    async def get_commands(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0, verify=self._verify()) as c:
            r = await c.get(
                f"{self.base_url}/api/devices/commands",
                headers=self._headers(),
            )
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else []

    async def report_command(
        self,
        command_id: str,
        status: str,
        result: dict | None = None,
    ) -> dict:
        async with httpx.AsyncClient(timeout=10.0, verify=self._verify()) as c:
            r = await c.post(
                f"{self.base_url}/api/devices/commands/result",
                headers=self._headers(),
                json={"command_id": command_id, "status": status, "result": result or {}},
            )
            r.raise_for_status()
            return r.json()
