"""Upgrade recovery contracts; no test operates on a real process or hosts file."""
from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

import psutil
import pytest

from src import legacy_recovery
from src.legacy_recovery import LegacyRestrictionRecovery, RecoveryStateError

APP = r"C:\Games\Example.exe"
OTHER = r"C:\Games\Other.exe"


@dataclass
class FakeProcess:
    world: dict
    pid: int
    executable: str = APP
    created: float = 100.25
    stopped: bool = True
    resume_calls: int = 0
    deny_resume: bool = False
    deny_identity: bool = False
    owner: str = r"FAMILY\child"

    def is_running(self):
        return self.world.get(self.pid) is self

    def create_time(self):
        if self.deny_identity:
            raise psutil.AccessDenied(self.pid)
        return self.created

    def exe(self):
        return self.executable

    def status(self):
        return psutil.STATUS_STOPPED if self.stopped else psutil.STATUS_RUNNING

    def parents(self):
        return []

    def username(self):
        return self.owner

    def suspend(self):
        pytest.fail("screenshot review must never suspend a process")

    def resume(self):
        self.resume_calls += 1
        if self.deny_resume:
            raise psutil.AccessDenied(self.pid)
        self.stopped = False


@pytest.fixture
def endpoint(tmp_path, monkeypatch):
    processes = {}
    clock = [10_000.0]
    path = tmp_path / "state.json"
    hosts = tmp_path / "hosts"

    def lookup(pid):
        if pid not in processes:
            raise psutil.NoSuchProcess(pid)
        return processes[pid]

    def add(pid=44, **kwargs):
        process = FakeProcess(processes, pid, **kwargs)
        processes[pid] = process
        return process

    def make():
        return LegacyRestrictionRecovery(state_path=path, hosts_path=hosts)

    def seed(*owned, actions=None, phase="suspended"):
        state = legacy_recovery._empty_state()
        state["actions"] = actions or {
            "pause-1": {"type": "pause_app", "target": APP, "expires_at": 99_999, "status": "active"},
        }
        for process in owned:
            record = {
                "pid": process.pid, "create_time": process.created,
                "exe": legacy_recovery._executable_key(process.executable), "phase": phase,
            }
            state["processes"][legacy_recovery._identity_key(record)] = record
        path.write_text(json.dumps(state), encoding="utf-8")
        return state

    monkeypatch.setattr(psutil, "Process", lookup)
    monkeypatch.setattr(psutil, "process_iter", lambda *_args: pytest.fail("recovery must not discover new processes"))
    monkeypatch.setattr(legacy_recovery, "_is_windows", lambda: True)
    monkeypatch.setattr(legacy_recovery.time, "time", lambda: clock[0])
    return SimpleNamespace(
        processes=processes, clock=clock, add=add, make=make, recovery=make(), seed=seed,
        path=path, hosts=hosts,
    )


def saved(endpoint):
    return json.loads(endpoint.path.read_text("utf-8"))


def undo(recovery, command_id="undo-1", original_id="pause-1", target=APP, action="pause_app"):
    return recovery.execute({
        "command_id": command_id, "command_type": "undo_action", "payload": {
            "original_action": action, "target": target, "original_command_id": original_id,
        },
    })


@pytest.mark.parametrize("action", ["pause_app", "block_domain", "show_child_prompt", "set_time_limit", "unknown"])
def test_new_restrictions_are_unconditionally_unavailable(endpoint, action):
    process = endpoint.add(stopped=False)
    endpoint.hosts.write_bytes(b"127.0.0.1 existing.test\n")
    with pytest.raises(ValueError, match="unavailable in screenshot review mode"):
        endpoint.recovery.execute({
            "command_id": "new-1", "command_type": action,
            "payload": {"target": APP, "duration_seconds": 900, "message": "ignored"},
        })
    assert not endpoint.path.exists()
    assert process.stopped is False
    assert endpoint.hosts.read_bytes() == b"127.0.0.1 existing.test\n"


def test_all_overlapping_legacy_leases_release_before_old_deadline(endpoint):
    process = endpoint.add()
    state = endpoint.seed(process)
    state["actions"]["pause-2"] = {**state["actions"]["pause-1"], "expires_at": 199_999}
    endpoint.path.write_text(json.dumps(state), encoding="utf-8")
    result = endpoint.recovery.reconcile()
    assert result["resumed_processes"] == 1
    assert result["newly_suspended_processes"] == 0
    assert result["active_pause_leases"] == 0
    assert result["partial_failure"] is False
    assert all(item["status"] == "undone" for item in saved(endpoint)["actions"].values())
    assert saved(endpoint)["processes"] == {}
    endpoint.make().reconcile()
    assert process.resume_calls == 1


@pytest.mark.parametrize("created,executable", [(101.0, APP), (100.25, OTHER)])
def test_identity_reuse_never_resumes_a_different_process(endpoint, created, executable):
    previous = endpoint.add()
    endpoint.seed(previous)
    replacement = endpoint.add(created=created, executable=executable)
    result = endpoint.make().reconcile()
    assert result["stale_process_records"] == 1
    assert replacement.resume_calls == previous.resume_calls == 0
    assert saved(endpoint)["processes"] == {}


def test_exited_and_already_running_records_need_no_resume(endpoint):
    exited = endpoint.add()
    running = endpoint.add(45, stopped=False)
    endpoint.seed(exited, running)
    del endpoint.processes[exited.pid]
    result = endpoint.recovery.reconcile()
    assert result["stale_process_records"] == 1
    assert result["resumed_processes"] == 0
    assert running.resume_calls == exited.resume_calls == 0
    assert saved(endpoint)["processes"] == {}


def test_unowned_suspended_process_is_never_adopted(endpoint):
    process = endpoint.add()
    result = endpoint.recovery.reconcile()
    assert result["resumed_processes"] == 0
    assert process.resume_calls == 0
    assert process.stopped is True


@pytest.mark.parametrize("phase", ["suspend_pending", "suspended", "resume_pending"])
def test_every_owned_legacy_phase_becomes_release_only(endpoint, phase):
    process = endpoint.add()
    endpoint.seed(process, phase=phase)
    result = endpoint.make().reconcile()
    assert result["resumed_processes"] == 1
    assert result["active_pause_leases"] == 0
    assert saved(endpoint)["processes"] == {}


@pytest.mark.parametrize("owner,executable", [
    (r"NT AUTHORITY\SYSTEM", APP), (r"NT SERVICE\Synthetic", APP),
    (r"FAMILY\child", r"C:\Windows\System32\lsass.exe"),
    (r"FAMILY\child", r"C:\GuardianNode\GuardianNode.exe"),
])
def test_protected_process_identity_is_preserved_without_operation(endpoint, owner, executable):
    process = endpoint.add(owner=owner, executable=executable)
    endpoint.seed(process)
    result = endpoint.recovery.reconcile()
    assert result["skipped_protected_processes"] == 1
    assert result["pending_resume_processes"] == 1
    assert result["partial_failure"] is True
    assert process.resume_calls == 0
    assert len(saved(endpoint)["processes"]) == 1


@pytest.mark.parametrize("failure", ["deny_resume", "deny_identity"])
def test_failed_release_retries_across_restart(endpoint, failure):
    process = endpoint.add(**{failure: True})
    endpoint.seed(process)
    result = endpoint.recovery.reconcile()
    assert result["failed_processes"] == 1
    assert result["pending_resume_processes"] == 1
    assert result["retryable"] is True
    assert result["partial_failure"] is True
    setattr(process, failure, False)
    retried = endpoint.make().reconcile()
    assert retried["resumed_processes"] == 1
    assert saved(endpoint)["processes"] == {}


def test_release_intent_must_persist_before_process_operation(endpoint, monkeypatch):
    process = endpoint.add()
    endpoint.seed(process)
    before = endpoint.path.read_bytes()
    monkeypatch.setattr(endpoint.recovery, "_save_state", lambda _state: (_ for _ in ()).throw(RecoveryStateError("disk full")))
    with pytest.raises(RecoveryStateError) as caught:
        endpoint.recovery.reconcile()
    assert caught.value.result["persistence_failed"] is True
    assert process.resume_calls == 0
    assert endpoint.path.read_bytes() == before


def test_completed_resume_with_failed_journal_cleanup_does_not_repeat(endpoint, monkeypatch):
    process = endpoint.add()
    endpoint.seed(process)
    save = endpoint.recovery._save_state

    def fail_cleanup(state):
        if not state["processes"]:
            raise RecoveryStateError("disk full")
        save(state)

    monkeypatch.setattr(endpoint.recovery, "_save_state", fail_cleanup)
    with pytest.raises(RecoveryStateError) as caught:
        endpoint.recovery.reconcile()
    assert caught.value.result["resumed_processes"] == 1
    assert process.resume_calls == 1
    assert len(saved(endpoint)["processes"]) == 1
    endpoint.make().reconcile()
    assert process.resume_calls == 1
    assert saved(endpoint)["processes"] == {}


def test_pid_only_legacy_records_are_retained_without_guessing(endpoint):
    process = endpoint.add()
    original = json.dumps({"old": {"type": "pause_app", "target": APP, "pids": [process.pid], "expires_at": 10}})
    endpoint.path.write_text(original, encoding="utf-8")
    result = endpoint.recovery.reconcile()
    assert result["legacy_unverified_processes"] == 1
    assert result["partial_failure"] is True
    assert process.resume_calls == 0
    assert endpoint.path.read_text("utf-8") == original
    endpoint.clock[0] += 30 * 86400
    assert endpoint.make().reconcile()["legacy_unverified_processes"] == 1


@pytest.mark.parametrize("content", ["{broken", "[]", '{"wrong":{"type":"pause_app","target":"bad"}}', '{"version":99,"actions":{},"processes":{}}'])
def test_corrupt_journal_is_preserved_without_guessing(endpoint, content):
    process = endpoint.add()
    endpoint.path.write_text(content, encoding="utf-8")
    with pytest.raises(RecoveryStateError, match="preserved for recovery"):
        endpoint.recovery.reconcile()
    assert endpoint.path.read_text("utf-8") == content
    assert process.resume_calls == 0


def test_undo_receipt_is_idempotent_and_retired_leases_cannot_reactivate(endpoint):
    process = endpoint.add()
    endpoint.seed(process)
    first = undo(endpoint.recovery)
    assert first["undone"] == 1
    assert first["resumed_processes"] == 1
    again = undo(endpoint.make())
    assert again["idempotent_replay"] is True
    assert again["undone"] == 1
    assert process.resume_calls == 1
    with pytest.raises(ValueError, match="different action"):
        undo(endpoint.make(), target=OTHER)


def test_undo_cannot_resume_an_unrecorded_target(endpoint):
    process = endpoint.add()
    result = undo(endpoint.recovery)
    assert result["undone"] == result["resumed_processes"] == 0
    assert process.resume_calls == 0


def test_undo_rejects_nonreversible_commands(endpoint):
    with pytest.raises(ValueError, match="not reversible"):
        undo(endpoint.recovery, action="show_child_prompt")


def test_domain_recovery_preserves_unrelated_bytes_and_cleans_orphaned_owned_lines(endpoint):
    unrelated = (
        b"# locally edited \xff\r\n127.0.0.1 existing.test # user entry\n"
        b"127.0.0.1 aliases.test other.test # GuardianNode old-1\r\n"
        b"10.0.0.2 private.test # GuardianNode old-2\n"
        b"# GuardianNode old-3\n"
    )
    owned = b"127.0.0.1 example.com # GuardianNode old-1\r\n::1 example.com # GuardianNode old-1\n"
    endpoint.hosts.write_bytes(unrelated + owned)
    # The old implementation wrote hosts before journal; cover that crash gap.
    assert not endpoint.path.exists()
    result = endpoint.recovery.reconcile()
    assert result["removed_domain_entries"] == 2
    assert result["pending_domain_blocks"] == 0
    assert endpoint.hosts.read_bytes() == unrelated
    assert endpoint.make().reconcile()["removed_domain_entries"] == 0


def test_old_domain_journal_becomes_undone_after_owned_cleanup(endpoint):
    endpoint.path.write_text(json.dumps({"old-1": {"type": "block_domain", "target": "example.com"}}))
    endpoint.hosts.write_bytes(b"127.0.0.1 example.com # GuardianNode old-1\n")
    result = endpoint.recovery.reconcile()
    assert result["removed_domain_entries"] == 1
    assert saved(endpoint)["actions"]["old-1"]["status"] == "undone"
    assert endpoint.hosts.read_bytes() == b""


def test_hosts_failure_stays_visible_and_retries(endpoint, monkeypatch):
    endpoint.seed(actions={"old-1": {"type": "block_domain", "target": "example.com", "status": "active"}})
    endpoint.hosts.write_bytes(b"127.0.0.1 example.com # GuardianNode old-1\n")
    monkeypatch.setattr(endpoint.recovery, "_remove_owned_hosts_entries", lambda: (_ for _ in ()).throw(OSError("locked")))
    result = endpoint.recovery.reconcile()
    assert result["pending_domain_blocks"] == 1
    assert result["retryable"] is result["partial_failure"] is True
    assert saved(endpoint)["actions"]["old-1"]["status"] == "active"
    assert endpoint.make().reconcile()["removed_domain_entries"] == 1
    assert saved(endpoint)["actions"]["old-1"]["status"] == "undone"


def test_hosts_editor_change_is_not_overwritten(endpoint, monkeypatch):
    original = b"127.0.0.1 example.com # GuardianNode old-1\n"
    changed = original + b"10.0.0.1 edited.test\n"
    endpoint.hosts.write_bytes(original)
    original_copy = legacy_recovery.shutil.copymode

    def edit_after_temp_write(source, target):
        original_copy(source, target)
        endpoint.hosts.write_bytes(changed)

    monkeypatch.setattr(legacy_recovery.shutil, "copymode", edit_after_temp_write)
    result = endpoint.recovery.reconcile()
    assert result["pending_domain_blocks"] == 1
    assert endpoint.hosts.read_bytes() == changed
    assert not list(endpoint.hosts.parent.glob("hosts.guardiannode-*.tmp"))


@pytest.mark.parametrize("operation", ["fsync", "replace"])
def test_failed_atomic_journal_write_preserves_prior_bytes(endpoint, monkeypatch, operation):
    process = endpoint.add()
    endpoint.seed(process)
    original = endpoint.path.read_bytes()
    monkeypatch.setattr(legacy_recovery.os, operation, lambda *_args: (_ for _ in ()).throw(OSError("locked")))
    with pytest.raises(RecoveryStateError):
        endpoint.recovery.reconcile()
    assert endpoint.path.read_bytes() == original
    assert process.resume_calls == 0
    assert not list(endpoint.path.parent.glob("enforcement-*.tmp"))


def test_missing_hosts_is_not_created_by_recovery(endpoint):
    endpoint.recovery.reconcile()
    assert not endpoint.hosts.exists()


def test_non_windows_recovery_has_no_side_effects(endpoint, monkeypatch):
    endpoint.path.write_text("broken")
    monkeypatch.setattr(legacy_recovery, "_is_windows", lambda: False)
    assert endpoint.recovery.reconcile() is None
    assert endpoint.path.read_text() == "broken"


def test_legacy_targets_still_require_exact_safe_shapes():
    assert legacy_recovery.validate_executable(APP) == APP
    assert legacy_recovery.validate_domain("Example.COM.") == "example.com"
    for unsafe in (r"Example.exe", r"C:\Games\..\cmd.exe", r"C:\Games\notes.txt"):
        with pytest.raises(ValueError):
            legacy_recovery.validate_executable(unsafe)
    for unsafe in ("https://example.com", "*.example.com", "localhost", "example.com/path"):
        with pytest.raises(ValueError):
            legacy_recovery.validate_domain(unsafe)
