from __future__ import annotations

import pytest

from src.broker_protocol import (
    MAX_SCREENSHOT_BYTES,
    ProtocolError,
    decode_frame,
    encode_frame,
    image_to_b64,
    make_request,
    parse_request,
)


def test_protocol_round_trip_and_parse() -> None:
    message = make_request("health")
    decoded = decode_frame(encode_frame(message))
    request = parse_request(decoded)
    assert request.action == "health"
    assert request.request_id == message["request_id"]


def test_protocol_allows_capture_config_without_payload() -> None:
    request = parse_request(make_request("capture_config"))
    assert request.action == "capture_config"
    assert request.payload == {}


def test_child_request_protocol_limits_content_and_profile_authority() -> None:
    request = parse_request(make_request("child_request_create", {
        "request_type": "site_exception", "target": "example.test", "reason": "school project",
    }))
    assert request.payload["request_type"] == "site_exception"
    parse_request(make_request("child_request_list"))
    for payload in (
        {"request_type": "site_exception", "profile_id": "another-child"},
        {"request_type": "site_exception", "reason": "x" * 4097},
        {"request_type": "arbitrary"},
    ):
        with pytest.raises(ProtocolError):
            parse_request(make_request("child_request_create", payload))
    with pytest.raises(ProtocolError):
        parse_request(make_request("child_request_list", {"device_id": "another-device"}))


def test_protocol_rejects_unknown_action() -> None:
    message = make_request("health")
    message["action"] = "read_device_token"
    with pytest.raises(ProtocolError):
        parse_request(message)


def test_protocol_rejects_oversized_screenshot() -> None:
    with pytest.raises(ProtocolError):
        image_to_b64(b"x" * (MAX_SCREENSHOT_BYTES + 1))


def test_protocol_rejects_bad_frame_size() -> None:
    frame = encode_frame(make_request("health"))[:-1]
    with pytest.raises(ProtocolError):
        decode_frame(frame)
