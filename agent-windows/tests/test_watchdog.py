from __future__ import annotations

from pathlib import Path

from src import watchdog


class FakeSessionApi:
    def __init__(
        self,
        *,
        active_sessions: set[int] | None,
        process_sessions: dict[str, set[int] | None],
        launch_result: bool = True,
        launch_results: dict[int, bool] | None = None,
    ) -> None:
        self.active_sessions = active_sessions
        self.process_sessions = process_sessions
        self.launch_result = launch_result
        self.launch_results = launch_results or {}
        self.launches: list[tuple[int, Path]] = []

    def active_user_session_ids(self) -> set[int] | None:
        return self.active_sessions

    def process_session_ids(self, image: str) -> set[int] | None:
        return self.process_sessions.get(image, set())

    def launch_in_session(self, session_id: int, executable: Path) -> bool:
        self.launches.append((session_id, executable))
        if session_id in self.launch_results:
            return self.launch_results[session_id]
        return self.launch_result


def test_watchdog_launches_missing_processes_in_exact_active_sessions(monkeypatch):
    fake = FakeSessionApi(
        active_sessions={1, 3},
        process_sessions={
            "GuardianNodeAgent.exe": {1},
            "GuardianNodeTray.exe": {3},
        },
    )
    task_runs: list[str] = []
    monkeypatch.setattr(watchdog.os, "name", "nt")
    monkeypatch.setattr(watchdog, "_maintenance_mode_active", lambda: False)
    monkeypatch.setattr(watchdog, "_resolve_watched_exe", lambda image: Path(f"C:/GN/{image}"))
    monkeypatch.setattr(watchdog, "_task_run_windows", task_runs.append)

    watchdog.watchdog_once(api=fake)

    assert fake.launches == [
        (3, Path("C:/GN/GuardianNodeAgent.exe")),
        (1, Path("C:/GN/GuardianNodeTray.exe")),
    ]
    assert task_runs == []


def test_watchdog_falls_back_to_task_when_exact_session_launch_fails(monkeypatch):
    fake = FakeSessionApi(
        active_sessions={7},
        process_sessions={"GuardianNodeAgent.exe": set(), "GuardianNodeTray.exe": {7}},
        launch_result=False,
    )
    task_runs: list[str] = []
    monkeypatch.setattr(watchdog.os, "name", "nt")
    monkeypatch.setattr(watchdog, "_maintenance_mode_active", lambda: False)
    monkeypatch.setattr(watchdog, "_resolve_watched_exe", lambda image: Path(f"C:/GN/{image}"))
    monkeypatch.setattr(watchdog, "_task_run_windows", task_runs.append)

    watchdog.watchdog_once(api=fake)

    assert fake.launches == [(7, Path("C:/GN/GuardianNodeAgent.exe"))]
    assert task_runs == ["GuardianNodeAgent"]


def test_watchdog_falls_back_when_one_missing_session_launch_fails(monkeypatch):
    fake = FakeSessionApi(
        active_sessions={7, 8},
        process_sessions={"GuardianNodeAgent.exe": set(), "GuardianNodeTray.exe": {7, 8}},
        launch_results={7: True, 8: False},
    )
    task_runs: list[str] = []
    monkeypatch.setattr(watchdog.os, "name", "nt")
    monkeypatch.setattr(watchdog, "_maintenance_mode_active", lambda: False)
    monkeypatch.setattr(watchdog, "_resolve_watched_exe", lambda image: Path(f"C:/GN/{image}"))
    monkeypatch.setattr(watchdog, "_task_run_windows", task_runs.append)

    watchdog.watchdog_once(api=fake)

    assert fake.launches == [
        (7, Path("C:/GN/GuardianNodeAgent.exe")),
        (8, Path("C:/GN/GuardianNodeAgent.exe")),
    ]
    assert task_runs == ["GuardianNodeAgent"]


def test_watchdog_skips_user_processes_when_no_active_session(monkeypatch):
    fake = FakeSessionApi(
        active_sessions=set(),
        process_sessions={"GuardianNodeAgent.exe": set(), "GuardianNodeTray.exe": set()},
    )
    task_runs: list[str] = []
    monkeypatch.setattr(watchdog.os, "name", "nt")
    monkeypatch.setattr(watchdog, "_maintenance_mode_active", lambda: False)
    monkeypatch.setattr(watchdog, "_task_run_windows", task_runs.append)

    watchdog.watchdog_once(api=fake)

    assert fake.launches == []
    assert task_runs == []


def test_watchdog_pauses_repairs_during_installer_maintenance(monkeypatch):
    fake = FakeSessionApi(
        active_sessions={1},
        process_sessions={"GuardianNodeAgent.exe": set(), "GuardianNodeTray.exe": set()},
    )
    task_runs: list[str] = []
    service_starts: list[str] = []
    monkeypatch.setattr(watchdog.os, "name", "nt")
    monkeypatch.setattr(watchdog, "_maintenance_mode_active", lambda: True)
    monkeypatch.setattr(watchdog, "_task_run_windows", task_runs.append)
    monkeypatch.setattr(watchdog, "_service_running_windows", lambda name: False)
    monkeypatch.setattr(watchdog, "_service_start_windows", service_starts.append)

    watchdog.watchdog_once(peer_service="GuardianNodeWatchdog2", api=fake)

    assert fake.launches == []
    assert task_runs == []
    assert service_starts == []
