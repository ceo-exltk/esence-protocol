"""
esence/protocol/message.py — Modelos Pydantic v2 para el protocolo Esence over ANP
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class MessageType(str, Enum):
    THREAD_MESSAGE = "thread_message"
    THREAD_REPLY = "thread_reply"
    PEER_INTRO = "peer_intro"
    CAPACITY_STATUS = "capacity_status"


class MessageStatus(str, Enum):
    PENDING_HUMAN_REVIEW = "pending_human_review"
    APPROVED = "approved"
    SENT = "sent"
    ANSWERED = "answered"
    REJECTED = "rejected"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class EsenceMessage(BaseModel):
    """Mensaje base del protocolo Esence v0.2."""

    esence_version: str = "0.2"
    type: MessageType
    thread_id: str = Field(default_factory=_new_uuid)
    from_did: str
    to_did: str
    content: str
    status: MessageStatus = MessageStatus.PENDING_HUMAN_REVIEW
    timestamp: str = Field(default_factory=_utcnow)
    signature: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"use_enum_values": True}

    def signable_bytes(self) -> bytes:
        """Bytes canónicos para firmar (sin el campo signature)."""
        data = self.model_dump(exclude={"signature"})
        # Orden determinístico para serialización
        import json
        return json.dumps(data, sort_keys=True, ensure_ascii=False).encode()


class ThreadMessage(EsenceMessage):
    """Mensaje que inicia un hilo de conversación entre nodos."""

    type: Literal[MessageType.THREAD_MESSAGE] = MessageType.THREAD_MESSAGE
    subject: str = ""

    model_config = {"use_enum_values": True}


class ThreadReply(EsenceMessage):
    """Respuesta dentro de un hilo existente."""

    type: Literal[MessageType.THREAD_REPLY] = MessageType.THREAD_REPLY
    in_reply_to: str | None = None  # message ID

    model_config = {"use_enum_values": True}


class PeerIntro(EsenceMessage):
    """Introducción entre nodos — intercambio de identidad y peer list."""

    type: Literal[MessageType.PEER_INTRO] = MessageType.PEER_INTRO
    public_key: str = ""          # Ed25519 public key en base64url
    known_peers: list[str] = Field(default_factory=list)  # lista de DIDs

    model_config = {"use_enum_values": True}


class CapacityStatus(EsenceMessage):
    """Estado de capacidad del nodo — para coordinación de la red."""

    type: Literal[MessageType.CAPACITY_STATUS] = MessageType.CAPACITY_STATUS
    available_pct: float = 0.0     # % de capacidad disponible para la red
    monthly_remaining: int = 0     # tokens restantes en el mes

    model_config = {"use_enum_values": True}

    @field_validator("available_pct")
    @classmethod
    def clamp_pct(cls, v: float) -> float:
        return max(0.0, min(100.0, v))


def parse_message(data: dict[str, Any]) -> EsenceMessage:
    """Parsea un dict a la subclase correcta según el campo type."""
    msg_type = data.get("type")
    mapping = {
        MessageType.THREAD_MESSAGE: ThreadMessage,
        MessageType.THREAD_REPLY: ThreadReply,
        MessageType.PEER_INTRO: PeerIntro,
        MessageType.CAPACITY_STATUS: CapacityStatus,
    }
    cls = mapping.get(msg_type, EsenceMessage)
    return cls.model_validate(data)
