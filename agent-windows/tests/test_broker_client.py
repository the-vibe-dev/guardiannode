from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from src.broker_client import BrokerClient, BrokerUnavailable
from src.broker_protocol import MAX_MESSAGE_BYTES, ProtocolError, encode_frame, make_response


def _response_reader(monkeypatch, chunks: list[bytes]):
    reads: list[int] = []

    def read(_handle, size: int):
        reads.append(size)
        chunk = chunks.pop(0)
        assert len(chunk) <= size
        return 0, chunk

    monkeypatch.setitem(sys.modules, "win32file", SimpleNamespace(ReadFile=read))
    monkeypatch.setitem(sys.modules, "win32pipe", SimpleNamespace(
        PeekNamedPipe=lambda *_args: (b"", max(1, len(chunks[0])) if chunks else 0, 0),
    ))
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


def test_broker_client_rejects_pipe_not_owned_by_system(monkeypatch):
    fake_security = SimpleNamespace(
        SE_KERNEL_OBJECT=1,
        OWNER_SECURITY_INFORMATION=2,
        GetSecurityInfo=lambda *_args: ("fake-user", None, None, None, None),
        ConvertSidToStringSid=lambda owner: owner,
    )
    monkeypatch.setitem(sys.modules, "win32security", fake_security)
    with pytest.raises(BrokerUnavailable, match="not owned by SYSTEM"):
        BrokerClient._verify_broker_owner(object())


def test_response_reader_times_out_when_broker_stays_silent(monkeypatch):
    from src import broker_client

    _response_reader(monkeypatch, [])
    ticks = iter([0.0, 6.0])
    monkeypatch.setattr(broker_client.time, "monotonic", lambda: next(ticks))
    with pytest.raises(BrokerUnavailable, match="deadline"):
        BrokerClient._read_response(object(), "request-1")
