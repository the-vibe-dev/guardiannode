from src.hardware_probe import probe
from src.hardware_tiers import select_tier


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


def test_tier_boundaries_are_conservative_for_current_vision_model():
    expected = {
        0: "text_only",
        6: "text_only",
        8: "text_only",
        10: "text_only",
        11: "text_only",
        12: "vision_only",
        15: "vision_only",
        16: "full",
        24: "full",
    }
    for vram_gb, tier in expected.items():
        selected, _, text_model, vision_model, _ = select_tier(16, vram_gb)
        assert selected == tier
        if tier == "full":
            assert text_model and vision_model
        elif tier == "vision_only":
            assert vision_model and text_model is None
        else:
            assert vision_model is None
