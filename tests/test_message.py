"""
tests/test_message.py — Tests de modelos Pydantic del protocolo Esense
"""
from __future__ import annotations

import json

import pytest

from esense.protocol.message import (
    EsenseMessage,
    MessageStatus,
    MessageType,
    PeerIntro,
    ThreadMessage,
    ThreadReply,
    parse_message,
)


def _base_dict(**kwargs) -> dict:
    return {
        "type": "thread_message",
        "from_did": "did:wba:localhost:alice",
        "to_did": "did:wba:localhost:bob",
        "content": "Hola",
        **kwargs,
    }


def test_thread_message_defaults():
    msg = ThreadMessage(
        from_did="did:wba:localhost:alice",
        to_did="did:wba:localhost:bob",
        content="Hola",
    )
    assert msg.esense_version == "0.2"
    assert msg.type == MessageType.THREAD_MESSAGE
    assert msg.status == MessageStatus.PENDING_HUMAN_REVIEW
    assert msg.thread_id  # debe tener UUID generado
    assert msg.timestamp


def test_message_status_enum_has_auto_approved():
    assert MessageStatus.AUTO_APPROVED == "auto_approved"


def test_signable_bytes_excludes_signature():
    msg = ThreadMessage(
        from_did="did:wba:localhost:alice",
        to_did="did:wba:localhost:bob",
        content="Test",
        signature="some_sig",
    )
    raw = msg.signable_bytes()
    parsed = json.loads(raw.decode())
    assert "signature" not in parsed
    assert "content" in parsed


def test_signable_bytes_deterministic():
    msg = ThreadMessage(
        from_did="did:wba:localhost:alice",
        to_did="did:wba:localhost:bob",
        content="Test",
    )
    assert msg.signable_bytes() == msg.signable_bytes()


def test_parse_message_thread_message():
    data = _base_dict()
    msg = parse_message(data)
    assert isinstance(msg, ThreadMessage)
    assert msg.from_did == "did:wba:localhost:alice"


def test_parse_message_thread_reply():
    data = _base_dict(type="thread_reply", in_reply_to="some-uuid")
    msg = parse_message(data)
    assert isinstance(msg, ThreadReply)


def test_parse_message_peer_intro():
    data = _base_dict(
        type="peer_intro",
        public_key="abc123",
        known_peers=["did:wba:localhost:carol"],
    )
    msg = parse_message(data)
    assert isinstance(msg, PeerIntro)
    assert msg.known_peers == ["did:wba:localhost:carol"]


def test_parse_message_unknown_type_raises():
    """parse_message() con tipo desconocido lanza ValidationError (EsenseMessage valida el enum)."""
    from pydantic import ValidationError

    data = _base_dict(type="thread_message")
    data["type"] = "unknown_type"
    with pytest.raises(ValidationError):
        parse_message(data)


def test_message_serialization_round_trip():
    msg = ThreadMessage(
        from_did="did:wba:localhost:alice",
        to_did="did:wba:localhost:bob",
        content="Round trip",
    )
    dumped = msg.model_dump()
    loaded = parse_message(dumped)
    assert loaded.content == "Round trip"
    assert loaded.from_did == msg.from_did
    assert loaded.thread_id == msg.thread_id


def test_message_status_values():
    assert MessageStatus.PENDING_HUMAN_REVIEW == "pending_human_review"
    assert MessageStatus.APPROVED == "approved"
    assert MessageStatus.SENT == "sent"
    assert MessageStatus.REJECTED == "rejected"
    assert MessageStatus.AUTO_APPROVED == "auto_approved"
