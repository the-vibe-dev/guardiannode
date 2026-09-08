from __future__ import annotations

import json

import pytest

from src.enforcement import WindowsEnforcer, validate_domain, validate_executable


def test_enforcement_revalidates_exact_targets() -> None:
    assert validate_executable(r"C:\Games\Example.exe") == r"C:\Games\Example.exe"
    assert validate_domain("Example.COM.") == "example.com"
    for unsafe in (r"Example.exe", r"C:\Games\..\cmd.exe", r"C:\Games\notes.txt"):
        with pytest.raises(ValueError):
            validate_executable(unsafe)
    for unsafe in ("https://example.com", "*.example.com", "localhost", "example.com/path"):
        with pytest.raises(ValueError):
            validate_domain(unsafe)


def test_domain_block_and_undo_only_touch_owned_lines(tmp_path) -> None:
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 existing.test # user entry\n", encoding="utf-8")
    state = tmp_path / "enforcement.json"
    enforcer = WindowsEnforcer(state_path=state, hosts_path=hosts)

    result = enforcer._block_domain("command-1", {"target": "Example.COM"})
    assert result == {"target": "example.com", "blocked": True}
    text = hosts.read_text("utf-8")
    assert "127.0.0.1 example.com # GuardianNode command-1" in text
    assert "::1 example.com # GuardianNode command-1" in text
    assert "existing.test # user entry" in text

    undone = enforcer._undo({"original_action": "block_domain", "target": "example.com"})
    assert undone["undone"] == 1
    assert "GuardianNode command-1" not in hosts.read_text("utf-8")
    assert "existing.test # user entry" in hosts.read_text("utf-8")
    assert json.loads(state.read_text("utf-8")) == {}


def test_unknown_or_irreversible_undo_is_rejected(tmp_path) -> None:
    hosts = tmp_path / "hosts"
    hosts.write_text("", encoding="utf-8")
    enforcer = WindowsEnforcer(state_path=tmp_path / "state.json", hosts_path=hosts)

    with pytest.raises(ValueError, match="not reversible"):
        enforcer._undo({"original_action": "show_child_prompt"})
