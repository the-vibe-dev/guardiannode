from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from src.broker_client import BrokerClient
from src.broker_protocol import MAX_MESSAGE_BYTES, ProtocolError, encode_frame, make_response


def _response_reader(monkeypatch, chunks: list[bytes]):
    reads: list[int] = []

    def read(_handle, size: int):
        reads.append(size)
        chunk = chunks.pop(0)
        assert len(chunk) <= size
        return 0, chunk

    monkeypatch.setitem(sys.modules, "win32file", SimpleNamespace(ReadFile=read))
    return reads


def test_response_reader_assembles_partial_header_and_body(monkeypatch):
    frame = encode_frame(make_response("request-1", ok=True, payload={"status": "queued"}))
    _response_reader(monkeypatch, [frame[:2], frame[2:4], frame[4:10], frame[10:]])
    assert BrokerClient._read_response(object(), "request-1")["payload"] == {"status": "queued"}


def test_response_reader_rejects_large_length_before_body_read(monkeypatch):
    reads = _response_reader(monkeypatch, [(MAX_MESSAGE_BYTES + 1).to_bytes(4, "big")])
    with pytest.raises(ProtocolError, match="too large"):
        BrokerClient._read_response(object(), "request-1")
    assert reads == [4]


@pytest.mark.parametrize("frame", [
    encode_frame(make_response("other-request", ok=True)),
    encode_frame({"version": 99, "request_id": "request-1", "ok": True, "payload": {}}),
    encode_frame({"version": 1, "request_id": "request-1", "ok": "yes", "payload": {}}),
])
def test_response_reader_rejects_unbound_or_invalid_response(monkeypatch, frame):
    _response_reader(monkeypatch, [frame[:4], frame[4:]])
    with pytest.raises(ProtocolError):
        BrokerClient._read_response(object(), "request-1")


def test_response_reader_rejects_disconnect_mid_frame(monkeypatch):
    frame = encode_frame(make_response("request-1", ok=True))
    _response_reader(monkeypatch, [frame[:4], frame[4:8], b""])
    with pytest.raises(ProtocolError, match="disconnected"):
        BrokerClient._read_response(object(), "request-1")
