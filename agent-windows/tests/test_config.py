from __future__ import annotations

from src.config import AgentConfig


def test_unquoted_yaml_age_group_is_normalized(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text("age_group: 10_13\n", encoding="utf-8")

    cfg = AgentConfig.from_path(path)

    assert cfg.age_group == "10_13"


def test_unknown_age_group_falls_back_to_default():
    assert AgentConfig(age_group="bogus").age_group == "10_13"


def test_old_enforcement_flag_cannot_enable_restrictions(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text("enforcement_enabled: true\n", encoding="utf-8")
    cfg = AgentConfig.from_path(path)
    assert not hasattr(cfg, "enforcement_enabled")
    cfg.save(path)
    assert "enforcement_enabled" not in path.read_text("utf-8")
