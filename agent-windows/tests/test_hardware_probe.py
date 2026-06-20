from src.hardware_probe import probe


def test_probe_returns_recognized_tier():
    info = probe()
    assert info.classifier_tier in {"full", "vision_only", "text_only"}
    assert info.cpu_cores >= 1
    assert info.ram_gb >= 1
    if info.classifier_tier == "full":
        assert info.text_model and info.vision_model
    elif info.classifier_tier == "vision_only":
        assert info.vision_model
    assert isinstance(info.reasoning, str) and info.reasoning
