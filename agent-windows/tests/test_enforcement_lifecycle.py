"""Portable lifecycle contracts; these tests never suspend a real process."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from types import SimpleNamespace

import psutil
import pytest

from src import enforcement
from src.enforcement import EnforcementStateError, WindowsEnforcer

APP = r"C:\Games\Example.exe"
OTHER = r"C:\Games\Different.exe"


@dataclass
class FakeProcess:
    world: dict
    pid: int
    executable: str = APP
    created: float = 100.25
    depth: int = 0
    suspend_calls: int = 0
    resume_calls: int = 0
    deny_suspend: bool = False
    deny_resume: bool = False
    deny_identity: bool = False
    partial_suspend_failure: bool = False
    hidden_exe: bool = False
    owner: str = r"FAMILY\child"
    deny_owner: bool = False
    ancestors: list = field(default_factory=list)
    before_suspend: object = None

    @property
    def info(self):
        return {"pid": self.pid, "exe": None if self.hidden_exe else self.executable}

    def is_running(self):
        return self.world.get(self.pid) is self

    def create_time(self):
        if self.deny_identity:
            raise psutil.AccessDenied(self.pid)
        return self.created

    def exe(self):
        if self.deny_identity:
            raise psutil.AccessDenied(self.pid)
        return self.executable

    def status(self):
        return psutil.STATUS_STOPPED if self.depth else psutil.STATUS_RUNNING

    def parents(self):
        return self.ancestors

    def username(self):
        if self.deny_owner:
            raise psutil.AccessDenied(self.pid)
        return self.owner

    def suspend(self):
        self.suspend_calls += 1
        if self.before_suspend is not None:
            self.before_suspend(self)
        # Like psutil's Windows Process methods, guard reuse at the OS boundary.
        if not self.is_running():
            raise psutil.NoSuchProcess(self.pid)
        if self.partial_suspend_failure:
            self.depth += 1
            raise psutil.AccessDenied(self.pid)
        if self.deny_suspend:
            raise psutil.AccessDenied(self.pid)
        self.depth += 1

    def resume(self):
        self.resume_calls += 1
        if not self.is_running():
            raise psutil.NoSuchProcess(self.pid)
        if self.deny_resume:
            raise psutil.AccessDenied(self.pid)
        self.depth = max(0, self.depth - 1)


@pytest.fixture
def endpoint(tmp_path, monkeypatch):
    processes = {}
    clock = [10_000.0]

    def lookup(pid):
        if pid not in processes:
            raise psutil.NoSuchProcess(pid)
        return processes[pid]

    def add(pid=44, **kwargs):
        process = FakeProcess(processes, pid, **kwargs)
        processes[pid] = process
        return process

    def make():
        return WindowsEnforcer(state_path=tmp_path / "state.json", hosts_path=tmp_path / "hosts")

    monkeypatch.setattr(psutil, "Process", lookup)
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: list(processes.values()))
    monkeypatch.setattr(enforcement, "_is_windows", lambda: True)
    monkeypatch.setattr(enforcement.time, "time", lambda: clock[0])
    return SimpleNamespace(
        processes=processes, clock=clock, add=add, make=make, enforcer=make(),
        path=tmp_path / "state.json",
    )


def pause(enforcer, command_id="pause-1", target=APP, duration=900):
    return enforcer.execute({
        "command_id": command_id, "command_type": "pause_app",
        "payload": {"target": target, "duration_seconds": duration},
    })


def undo(enforcer, command_id="undo-1", original_id=None, target=APP):
    payload = {"original_action": "pause_app", "target": target}
    if original_id is not None:
        payload["original_command_id"] = original_id
    return enforcer.execute({"command_id": command_id, "command_type": "undo_action", "payload": payload})


def saved(endpoint):
    return json.loads(endpoint.path.read_text("utf-8"))


def test_full_identity_is_durable_before_suspend_and_case_insensitive(endpoint):
    process = endpoint.add(executable=r"c:/GAMES/EXAMPLE.EXE")

    def verify_intent(proc):
        records = list(saved(endpoint)["processes"].values())
        assert records == [{
            "pid": proc.pid, "create_time": proc.created, "exe": r"c:\games\example.exe",
            "phase": "suspend_pending",
        }]

    process.before_suspend = verify_intent
    result = pause(endpoint.enforcer)
    assert result["suspended_processes"] == 1
    assert result["newly_suspended_processes"] == 1
    assert result["failed_processes"] == 0
    assert result["partial_failure"] is False
    assert list(saved(endpoint)["processes"].values())[0]["phase"] == "suspended"


def test_replay_and_broker_restart_do_not_extend_or_suspend_twice(endpoint):
    process = endpoint.add()
    first = pause(endpoint.enforcer)
    endpoint.clock[0] += 100
    replay = pause(endpoint.make())
    assert replay["idempotent_replay"] is True
    assert replay["expires_at"] == first["expires_at"]
    assert replay["newly_suspended_processes"] == 0
    assert process.suspend_calls == 1
    assert endpoint.make().reconcile()["suspended_processes"] == 1
    assert process.depth == 1


@pytest.mark.parametrize("created,executable", [(101.0, APP), (100.25, OTHER)])
def test_release_never_resumes_pid_reused_or_different_executable(endpoint, created, executable):
    previous = endpoint.add()
    pause(endpoint.enforcer)
    replacement = endpoint.add(created=created, executable=executable)
    endpoint.clock[0] += 901
    result = endpoint.make().reconcile()
    assert result["stale_process_records"] == 1
    assert replacement.resume_calls == 0
    assert previous.resume_calls == 0
    assert saved(endpoint)["processes"] == {}


def test_reused_pid_for_new_matching_process_is_restricted_during_active_lease(endpoint):
    previous = endpoint.add()
    pause(endpoint.enforcer)
    replacement = endpoint.add(created=101.0)
    result = endpoint.make().reconcile()
    assert result["stale_process_records"] == 1
    assert result["newly_suspended_processes"] == 1
    assert replacement.depth == 1
    assert replacement.resume_calls == previous.resume_calls == 0


def test_overlapping_expiry_keeps_one_shared_suspension(endpoint):
    process = endpoint.add()
    pause(endpoint.enforcer, "short", duration=900)
    pause(endpoint.enforcer, "long", duration=3600)
    endpoint.clock[0] += 901
    endpoint.make().reconcile()
    assert process.suspend_calls == 1
    assert process.resume_calls == 0
    assert saved(endpoint)["actions"]["short"]["status"] == "expired"
    endpoint.clock[0] += 2700
    endpoint.make().reconcile()
    assert process.resume_calls == 1
    assert process.depth == 0
    endpoint.make().reconcile()
    assert process.resume_calls == 1


def test_specific_undo_preserves_overlapping_pause(endpoint):
    process = endpoint.add()
    pause(endpoint.enforcer, "first")
    pause(endpoint.enforcer, "second")
    result = undo(endpoint.enforcer, original_id="first", target=r"c:\GAMES\example.exe")
    assert result["undone"] == 1
    assert result["suspended_processes"] == 1
    assert process.resume_calls == 0
    result = undo(endpoint.make(), command_id="undo-2", original_id="second")
    assert result["resumed_processes"] == 1
    assert process.resume_calls == 1


def test_legacy_target_wide_undo_is_idempotent_even_after_new_pause(endpoint):
    process = endpoint.add()
    pause(endpoint.enforcer, "first")
    pause(endpoint.enforcer, "second")
    result = undo(endpoint.enforcer)
    assert result["undone"] == 2
    assert process.resume_calls == 1
    pause(endpoint.enforcer, "third")
    replay = undo(endpoint.make())
    assert replay["idempotent_replay"] is True
    assert replay["undone"] == 2
    assert process.resume_calls == 1
    assert process.depth == 1
    assert saved(endpoint)["actions"]["third"]["status"] == "active"


def test_relaunch_is_restricted_without_expanding_to_other_executables(endpoint):
    original = endpoint.add()
    pause(endpoint.enforcer)
    relaunched = endpoint.add(pid=45)
    unrelated = endpoint.add(pid=46, executable=OTHER)
    result = endpoint.make().reconcile()
    assert result["newly_suspended_processes"] == 1
    assert result["suspended_processes"] == 2
    assert original.suspend_calls == relaunched.suspend_calls == 1
    assert unrelated.suspend_calls == 0
    endpoint.clock[0] += 901
    endpoint.make().reconcile()
    assert original.resume_calls == relaunched.resume_calls == 1
    assert unrelated.resume_calls == 0


def test_manually_resumed_app_is_restricted_again_under_same_parent_lease(endpoint):
    process = endpoint.add()
    pause(endpoint.enforcer)
    process.depth = 0
    result = endpoint.make().reconcile()
    assert result["newly_suspended_processes"] == 1
    assert process.suspend_calls == 2
    assert process.depth == 1


def test_expired_or_undone_command_replay_cannot_restart_pause(endpoint):
    process = endpoint.add()
    pause(endpoint.enforcer)
    endpoint.clock[0] += 901
    result = pause(endpoint.make())
    assert result["lease_status"] == "expired"
    assert process.suspend_calls == 1
    assert process.resume_calls == 1
    later = endpoint.add(pid=55)
    pause(endpoint.make())
    assert later.suspend_calls == 0


def test_external_suspension_is_never_adopted_or_resumed(endpoint):
    process = endpoint.add(depth=1)
    result = pause(endpoint.enforcer)
    assert result["already_suspended_elsewhere"] == 1
    assert result["suspended_processes"] == 0
    assert saved(endpoint)["processes"] == {}
    undo(endpoint.make())
    assert process.depth == 1
    assert process.suspend_calls == process.resume_calls == 0


@pytest.mark.parametrize("executable", [
    r"C:\Windows\System32\lsass.exe", r"C:\Windows\System32\svchost.exe",
    r"C:\Windows\explorer.exe", r"C:\Program Files\GuardianNode\GuardianNodeBroker.exe",
    r"C:\Program Files\GuardianNode\GuardianNodeAgent.exe",
    r"C:\Program Files\GuardianNode\GuardianNodeWatchdog.exe",
    r"C:\Program Files\GuardianNode\GuardianNodeTray.exe",
])
def test_protected_system_and_guardiannode_targets_rejected(endpoint, executable):
    process = endpoint.add(executable=executable)
    with pytest.raises(ValueError, match="cannot be paused"):
        pause(endpoint.enforcer, target=executable)
    assert process.suspend_calls == process.resume_calls == 0
    assert not endpoint.path.exists()


def test_own_process_and_ancestors_are_never_suspended(endpoint):
    own = endpoint.add(pid=os.getpid())
    parent = endpoint.add(pid=own.pid + 20)
    own.ancestors = [parent]
    result = pause(endpoint.enforcer)
    assert result["skipped_protected_processes"] == 2
    assert result["partial_failure"] is True
    assert own.suspend_calls == parent.suspend_calls == 0


@pytest.mark.parametrize("owner", [
    r"NT AUTHORITY\SYSTEM", r"NT AUTHORITY\LOCAL SERVICE",
    r"NT AUTHORITY\NETWORK SERVICE", r"NT SERVICE\SomeService",
])
def test_service_processes_are_protected_even_with_unrecognized_executable(endpoint, owner):
    process = endpoint.add(owner=owner)
    result = pause(endpoint.enforcer)
    assert result["skipped_protected_processes"] == 1
    assert result["partial_failure"] is True
    assert process.suspend_calls == process.resume_calls == 0


def test_unreadable_process_owner_cannot_be_suspended(endpoint):
    process = endpoint.add(deny_owner=True)
    result = pause(endpoint.enforcer)
    assert result["failed_processes"] == 1
    assert process.suspend_calls == 0


@pytest.mark.parametrize("corruption", [
    "{not json", "[]", '{"version": 999, "actions": {}, "processes": {}}',
    '{"version": 2, "actions": {}, "processes": {"wrong": {"pid": 44}}}',
    '{"wrong": {"type": "pause_app", "target": "bad"}}',
])
def test_corrupt_state_is_preserved_and_blocks_new_side_effects(endpoint, corruption):
    process = endpoint.add()
    endpoint.path.write_text(corruption, encoding="utf-8")
    with pytest.raises(EnforcementStateError, match="preserved for recovery"):
        pause(endpoint.enforcer)
    assert endpoint.path.read_text("utf-8") == corruption
    assert process.suspend_calls == process.resume_calls == 0


def test_legacy_pid_only_state_never_causes_resume_or_adoption(endpoint):
    process = endpoint.add(depth=1)
    endpoint.path.write_text(json.dumps({"old": {
        "type": "pause_app", "target": APP, "pids": [process.pid], "expires_at": 1000,
    }}), encoding="utf-8")
    result = endpoint.enforcer.reconcile()
    assert result["legacy_unverified_processes"] == 1
    assert result["partial_failure"] is True
    undo(endpoint.enforcer)
    assert process.resume_calls == process.suspend_calls == 0
    assert saved(endpoint)["actions"]["old"]["status"] == "legacy_unverified"


def test_suspend_access_denied_reports_partial_failure_and_retries(endpoint):
    okay = endpoint.add()
    denied = endpoint.add(pid=45, deny_suspend=True)
    result = pause(endpoint.enforcer)
    assert result["suspended_processes"] == 1
    assert result["failed_processes"] == 1
    assert result["partial_failure"] is result["retryable"] is True
    denied.deny_suspend = False
    result = endpoint.make().reconcile()
    assert result["suspended_processes"] == 2
    assert okay.suspend_calls == 1
    assert denied.depth == 1


def test_failed_resume_retains_identity_and_retries_after_restart(endpoint):
    process = endpoint.add()
    pause(endpoint.enforcer)
    process.deny_resume = True
    result = undo(endpoint.enforcer)
    assert result["undone"] == 1
    assert result["failed_processes"] == 1
    assert result["pending_resume_processes"] == 1
    assert result["partial_failure"] is True
    record = next(iter(saved(endpoint)["processes"].values()))
    assert record["pid"] == process.pid
    assert record["create_time"] == process.created
    assert record["phase"] == "resume_pending"
    process.deny_resume = False
    result = endpoint.make().reconcile()
    assert result["resumed_processes"] == 1
    assert result["pending_resume_processes"] == 0
    assert process.depth == 0
    assert saved(endpoint)["processes"] == {}


@pytest.mark.parametrize("release", ["undo", "expiry"])
def test_new_lease_preserves_suspension_after_previous_release_failed(endpoint, release):
    process = endpoint.add()
    pause(endpoint.enforcer, "old")
    process.deny_resume = True
    if release == "undo":
        undo(endpoint.enforcer, original_id="old")
    else:
        endpoint.clock[0] += 901
        endpoint.enforcer.reconcile()
    assert next(iter(saved(endpoint)["processes"].values()))["phase"] == "resume_pending"
    process.deny_resume = False
    previous_resume_calls = process.resume_calls
    result = pause(endpoint.make(), "new")
    assert result["suspended_processes"] == 1
    assert result["pending_resume_processes"] == 0
    assert process.resume_calls == previous_resume_calls
    assert process.suspend_calls == 1
    assert process.depth == 1
    undo(endpoint.make(), command_id="undo-new", original_id="new")
    assert process.depth == 0
    assert process.resume_calls == previous_resume_calls + 1


def test_inaccessible_identity_is_not_falsely_reported_as_suspended(endpoint):
    process = endpoint.add()
    pause(endpoint.enforcer)
    process.deny_identity = True
    result = endpoint.make().reconcile()
    assert result["failed_processes"] == 1
    assert result["suspended_processes"] == 0
    assert len(saved(endpoint)["processes"]) == 1
    endpoint.clock[0] += 901
    result = endpoint.make().reconcile()
    assert result["pending_resume_processes"] == 1
    process.deny_identity = False
    endpoint.make().reconcile()
    assert process.depth == 0


def test_pid_reuse_at_suspend_os_boundary_is_not_claimed(endpoint):
    process = endpoint.add()
    replacement = None

    def reuse(_):
        nonlocal replacement
        replacement = endpoint.add(created=200.0)

    process.before_suspend = reuse
    result = pause(endpoint.enforcer)
    assert result["suspended_processes"] == 0
    assert replacement.suspend_calls == replacement.resume_calls == 0
    endpoint.make().reconcile()
    assert replacement.suspend_calls == 1


def failing_writes(monkeypatch, enforcer, first_failure, *, every_later=True):
    original = enforcer._save_state
    calls = []

    def save(state):
        calls.append(1)
        if len(calls) == first_failure or (every_later and len(calls) >= first_failure):
            raise EnforcementStateError("synthetic disk full")
        return original(state)

    monkeypatch.setattr(enforcer, "_save_state", save)
    return original, calls


@pytest.mark.parametrize("first_failure", [1, 2])
def test_disk_failure_before_lease_or_identity_prevents_suspend(endpoint, monkeypatch, first_failure):
    process = endpoint.add()
    failing_writes(monkeypatch, endpoint.enforcer, first_failure)
    with pytest.raises(EnforcementStateError):
        pause(endpoint.enforcer)
    assert process.suspend_calls == process.resume_calls == 0
    if endpoint.path.exists():
        assert saved(endpoint)["processes"] == {}


def test_disk_failure_after_suspend_rolls_back_and_preserves_recovery_intent(endpoint, monkeypatch):
    process = endpoint.add()
    failing_writes(monkeypatch, endpoint.enforcer, 3)
    with pytest.raises(EnforcementStateError) as caught:
        pause(endpoint.enforcer)
    assert caught.value.result["rollback_succeeded"] is True
    assert caught.value.result["suspended_processes"] == 0
    assert caught.value.result["persistence_failed"] is True
    assert process.depth == 0
    assert process.resume_calls == 1
    record = next(iter(saved(endpoint)["processes"].values()))
    assert record["phase"] == "suspend_pending"
    # Recover the already-authorized lease without duplicating suspension.
    endpoint.make().reconcile()
    assert process.depth == 1
    endpoint.clock[0] += 901
    endpoint.make().reconcile()
    assert process.depth == 0


def test_disk_failure_with_failed_rollback_keeps_identity_until_release_possible(endpoint, monkeypatch):
    process = endpoint.add(deny_resume=True)
    failing_writes(monkeypatch, endpoint.enforcer, 3)
    with pytest.raises(EnforcementStateError) as caught:
        pause(endpoint.enforcer)
    assert caught.value.result["rollback_succeeded"] is False
    assert process.depth == 1
    assert len(saved(endpoint)["processes"]) == 1
    endpoint.clock[0] += 901
    result = endpoint.make().reconcile()
    assert result["pending_resume_processes"] == 1
    process.deny_resume = False
    endpoint.make().reconcile()
    assert process.depth == 0


def test_partially_failed_suspend_rolls_back_even_if_disk_now_fails(endpoint, monkeypatch):
    process = endpoint.add(partial_suspend_failure=True)
    failing_writes(monkeypatch, endpoint.enforcer, 3)
    with pytest.raises(EnforcementStateError) as caught:
        pause(endpoint.enforcer)
    assert caught.value.result["partial_failure"] is True
    assert caught.value.result["rollback_succeeded"] is True
    assert caught.value.result["pending_recovery_processes"] == 1
    assert process.depth == 0
    assert process.resume_calls == 1
    assert len(saved(endpoint)["processes"]) == 1


def test_crash_between_suspend_and_completion_is_recovered_without_double_suspend(endpoint, monkeypatch):
    class SimulatedCrash(BaseException):
        pass

    process = endpoint.add()
    original = endpoint.enforcer._save_state
    calls = []

    def crash_on_completion(state):
        calls.append(1)
        if len(calls) == 3:
            raise SimulatedCrash()
        original(state)

    monkeypatch.setattr(endpoint.enforcer, "_save_state", crash_on_completion)
    with pytest.raises(SimulatedCrash):
        pause(endpoint.enforcer)
    assert process.depth == 1
    assert next(iter(saved(endpoint)["processes"].values()))["phase"] == "suspend_pending"
    endpoint.make().reconcile()
    assert process.suspend_calls == 1
    endpoint.clock[0] += 901
    endpoint.make().reconcile()
    assert process.resume_calls == 1


def test_command_identity_collision_cannot_change_target_or_duration(endpoint):
    process = endpoint.add()
    pause(endpoint.enforcer)
    with pytest.raises(ValueError, match="different action"):
        pause(endpoint.enforcer, target=OTHER)
    with pytest.raises(ValueError, match="different action"):
        pause(endpoint.enforcer, duration=3600)
    assert process.suspend_calls == 1


def test_uninspectable_process_is_reported_without_claiming_full_scan(endpoint):
    endpoint.add()
    endpoint.add(pid=45, hidden_exe=True)
    result = pause(endpoint.enforcer)
    assert result["suspended_processes"] == 1
    assert result["uninspectable_processes"] == 1
    assert result["scan_complete"] is False


def test_no_running_match_keeps_explicit_lease_for_later_launch(endpoint):
    result = pause(endpoint.enforcer)
    assert result["lease_status"] == "active"
    assert result["suspended_processes"] == result["failed_processes"] == 0
    process = endpoint.add()
    endpoint.make().reconcile()
    assert process.depth == 1


@pytest.mark.parametrize("operation", ["fsync", "replace"])
def test_atomic_state_write_failure_preserves_previous_file(endpoint, monkeypatch, operation):
    process = endpoint.add()
    endpoint.enforcer._save_state(enforcement._empty_state())
    previous = endpoint.path.read_bytes()

    def fail(*_args, **_kwargs):
        raise OSError("synthetic storage failure")

    monkeypatch.setattr(enforcement.os, operation, fail)
    with pytest.raises(EnforcementStateError):
        pause(endpoint.enforcer)
    assert endpoint.path.read_bytes() == previous
    assert list(endpoint.path.parent.glob("enforcement-*.tmp")) == []
    assert process.suspend_calls == process.resume_calls == 0


def test_successful_resume_with_failed_journal_cleanup_is_not_repeated(endpoint, monkeypatch):
    process = endpoint.add()
    pause(endpoint.enforcer)
    failing_writes(monkeypatch, endpoint.enforcer, 3)
    with pytest.raises(EnforcementStateError) as caught:
        undo(endpoint.enforcer, original_id="pause-1")
    assert caught.value.result["undone"] == 1
    assert caught.value.result["resumed_processes"] == 1
    assert caught.value.result["pending_resume_processes"] == 1
    assert process.depth == 0
    assert process.resume_calls == 1
    endpoint.make().reconcile()
    assert process.resume_calls == 1
    assert saved(endpoint)["processes"] == {}
