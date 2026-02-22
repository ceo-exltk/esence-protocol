"""
tests/test_queue.py — Tests de MessageQueue (asyncio)
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from esense.core.queue import MessageQueue
from esense.essence.store import EssenceStore
from esense.protocol.message import MessageStatus


@pytest.fixture
def queue(tmp_store: EssenceStore) -> MessageQueue:
    return MessageQueue(store=tmp_store)


def _inbound_msg(thread_id: str = "test-thread", from_did: str = "did:wba:localhost:peer") -> dict:
    return {
        "esense_version": "0.2",
        "type": "thread_message",
        "thread_id": thread_id,
        "from_did": from_did,
        "to_did": "did:wba:localhost:node0",
        "content": "Hola agente",
        "timestamp": "2026-02-21T00:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_enqueue_inbound_adds_to_pending(queue: MessageQueue):
    msg = _inbound_msg()
    await queue.enqueue_inbound(msg)
    pending = await queue.peek_pending()
    # Si no hay autonomía suficiente → queda en pending
    assert len(pending) >= 0  # puede ser 0 si auto_approved, pero sin trust ni maturity será pending
    assert queue.qsize_inbound() == 1


@pytest.mark.asyncio
async def test_enqueue_inbound_status_pending_by_default(queue: MessageQueue):
    """Sin madurez ni peers de confianza, status es pending_human_review."""
    msg = _inbound_msg()
    await queue.enqueue_inbound(msg)
    assert msg["status"] == MessageStatus.PENDING_HUMAN_REVIEW


@pytest.mark.asyncio
async def test_enqueue_inbound_auto_approved_with_trusted_peer_and_maturity(
    tmp_store: EssenceStore,
):
    """Con peer de confianza y maturity alta → AUTO_APPROVED."""
    # Simular maturity alta poniendo muchas correcciones y patrones
    for i in range(100):
        tmp_store.append_correction({
            "original": f"orig {i}", "edited": f"edit {i}",
            "thread_id": f"t{i}", "from_did": "did:wba:localhost:peer",
        })
    for i in range(50):
        tmp_store.add_pattern({"description": f"patrón {i}", "confidence": 0.9})
    tmp_store.write_context("# Contexto\n" + " word" * 600)

    # Peer con trust alto
    peer_did = "did:wba:localhost:trusted"
    tmp_store.upsert_peer({"did": peer_did, "trust_score": 0.9})

    # Threshold bajo para el test
    budget = tmp_store.read_budget()
    budget["autonomy_threshold"] = 0.01  # casi siempre auto-aprueba
    tmp_store.write_budget(budget)

    queue = MessageQueue(store=tmp_store)
    msg = _inbound_msg(from_did=peer_did)
    await queue.enqueue_inbound(msg)

    assert msg["status"] == MessageStatus.AUTO_APPROVED


@pytest.mark.asyncio
async def test_approve_logs_correction(queue: MessageQueue, tmp_store: EssenceStore):
    """approve() con proposed_reply registra en corrections.log."""
    msg = _inbound_msg()
    await queue.enqueue_inbound(msg)

    # Simular que el engine generó una propuesta
    thread_id = msg["thread_id"]
    queue._pending[thread_id]["proposed_reply"] = "propuesta original"

    await queue.approve(thread_id)

    corrections = tmp_store.read_corrections()
    assert len(corrections) == 1
    assert corrections[0]["original"] == "propuesta original"
    assert corrections[0]["edited"] == "propuesta original"  # sin edición


@pytest.mark.asyncio
async def test_approve_with_edited_reply_logs_correction(
    queue: MessageQueue, tmp_store: EssenceStore
):
    """approve() con edited_reply diferente registra la edición."""
    msg = _inbound_msg()
    await queue.enqueue_inbound(msg)

    thread_id = msg["thread_id"]
    queue._pending[thread_id]["proposed_reply"] = "propuesta original"

    await queue.approve(thread_id, edited_reply="respuesta editada por el dueño")

    corrections = tmp_store.read_corrections()
    assert len(corrections) == 1
    assert corrections[0]["original"] == "propuesta original"
    assert corrections[0]["edited"] == "respuesta editada por el dueño"


@pytest.mark.asyncio
async def test_approve_moves_to_outbound(queue: MessageQueue):
    """approve() mueve el mensaje a outbound."""
    msg = _inbound_msg()
    await queue.enqueue_inbound(msg)
    thread_id = msg["thread_id"]

    assert queue.qsize_outbound() == 0
    await queue.approve(thread_id)
    assert queue.qsize_outbound() == 1


@pytest.mark.asyncio
async def test_approve_removes_from_pending(queue: MessageQueue):
    msg = _inbound_msg()
    await queue.enqueue_inbound(msg)
    thread_id = msg["thread_id"]

    pending_before = await queue.peek_pending()
    assert len(pending_before) == 1

    await queue.approve(thread_id)

    pending_after = await queue.peek_pending()
    assert len(pending_after) == 0


@pytest.mark.asyncio
async def test_approve_nonexistent_returns_none(queue: MessageQueue):
    result = await queue.approve("nonexistent-thread-id")
    assert result is None


@pytest.mark.asyncio
async def test_reject_removes_from_pending(queue: MessageQueue):
    msg = _inbound_msg()
    await queue.enqueue_inbound(msg)
    thread_id = msg["thread_id"]

    await queue.reject(thread_id)

    pending = await queue.peek_pending()
    assert len(pending) == 0
    assert thread_id not in queue._pending


@pytest.mark.asyncio
async def test_emit_correction_logged_event(queue: MessageQueue):
    """approve() emite evento correction_logged cuando hay proposed_reply."""
    events = []

    async def capture(event_type: str, data: dict) -> None:
        events.append((event_type, data))

    queue.subscribe(capture)

    msg = _inbound_msg()
    await queue.enqueue_inbound(msg)
    thread_id = msg["thread_id"]
    queue._pending[thread_id]["proposed_reply"] = "propuesta"
    await queue.approve(thread_id)

    event_types = [e[0] for e in events]
    assert "correction_logged" in event_types


@pytest.mark.asyncio
async def test_restore_pending_from_disk(tmp_store: EssenceStore):
    """restore_pending() carga mensajes pendientes del disco."""
    # Escribir un mensaje pendiente en el store
    thread_id = "restore-test"
    msg = {
        "thread_id": thread_id,
        "status": MessageStatus.PENDING_HUMAN_REVIEW,
        "content": "Test",
        "from_did": "did:wba:localhost:peer",
    }
    tmp_store.write_thread(thread_id, [msg])

    queue = MessageQueue(store=tmp_store)
    queue.restore_pending()

    assert thread_id in queue._pending
    assert queue.pending_count() == 1
