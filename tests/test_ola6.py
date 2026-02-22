"""
tests/test_ola6.py — Tests para Ola 6:
Thread history, context editor, typing indicator.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from fastapi.testclient import TestClient

from esense.core.identity import Identity
from esense.interface.server import create_app


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_node(store_dir: Path):
    """Crea un nodo con store real en tmp_path."""
    from esense.essence.store import EssenceStore
    from esense.protocol.peers import PeerManager
    from esense.core.queue import MessageQueue

    store = EssenceStore(store_dir=store_dir)
    store.initialize({
        "id": "did:wba:localhost:testnode",
        "name": "testnode",
        "domain": "localhost",
        "languages": ["es"],
        "values": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    node = MagicMock()
    node.identity = Identity.generate("testnode", "localhost")
    node.store = store
    node.peers = PeerManager(store)
    node.queue = MessageQueue(store)
    node.queue.restore_pending()

    # Wire get_recent_threads from real node method
    from esense.core.node import EsenseNode
    node.get_recent_threads = lambda limit=20: EsenseNode.get_recent_threads(node, limit)

    return node


def _write_thread(store, thread_id: str, messages: list[dict]) -> None:
    """Helper para escribir un thread en el store."""
    store.write_thread(thread_id, messages)


# ------------------------------------------------------------------
# A — TestApiThreads
# ------------------------------------------------------------------

class TestApiThreads:
    def test_get_threads_returns_list(self, tmp_path):
        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app)
        resp = client.get("/api/threads")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_threads_returns_empty_without_threads(self, tmp_path):
        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app)
        resp = client.get("/api/threads")
        assert resp.json() == []

    def test_get_threads_returns_metadata(self, tmp_path):
        node = _make_node(tmp_path)
        _write_thread(node.store, "thread-001", [
            {
                "thread_id": "thread-001",
                "from_did": "did:wba:alice.com:alice",
                "content": "Hola!",
                "status": "pending_human_review",
                "timestamp": "2026-02-22T10:00:00+00:00",
            }
        ])
        app = create_app(node=node)
        client = TestClient(app)
        resp = client.get("/api/threads")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        t = data[0]
        assert t["thread_id"] == "thread-001"
        assert t["from_did"] == "did:wba:alice.com:alice"
        assert "Hola!" in t["last_message"]
        assert t["status"] == "pending_human_review"
        assert t["message_count"] == 1

    def test_get_thread_by_id_returns_messages(self, tmp_path):
        node = _make_node(tmp_path)
        messages = [
            {
                "thread_id": "thread-002",
                "from_did": "did:wba:bob.com:bob",
                "content": "Primer mensaje",
                "status": "pending_human_review",
                "timestamp": "2026-02-22T11:00:00+00:00",
            },
            {
                "thread_id": "thread-002",
                "from_did": "did:wba:bob.com:bob",
                "content": "Segundo mensaje",
                "status": "answered",
                "timestamp": "2026-02-22T11:05:00+00:00",
            },
        ]
        _write_thread(node.store, "thread-002", messages)
        app = create_app(node=node)
        client = TestClient(app)
        resp = client.get("/api/threads/thread-002")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["content"] == "Primer mensaje"
        assert data[1]["content"] == "Segundo mensaje"

    def test_get_thread_by_id_returns_404_if_not_found(self, tmp_path):
        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app)
        resp = client.get("/api/threads/nonexistent-thread")
        assert resp.status_code == 404

    def test_get_threads_without_node_returns_empty(self):
        app = create_app(node=None)
        client = TestClient(app)
        resp = client.get("/api/threads")
        assert resp.status_code == 200
        assert resp.json() == []


# ------------------------------------------------------------------
# B — TestApiContext
# ------------------------------------------------------------------

class TestApiContext:
    def test_get_context_returns_content(self, tmp_path):
        node = _make_node(tmp_path)
        node.store.write_context("## Mi dominio\n\nExperto en sistemas distribuidos.")
        app = create_app(node=node)
        client = TestClient(app)
        resp = client.get("/api/context")
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert "Mi dominio" in data["content"]

    def test_get_context_returns_empty_string_if_no_file(self, tmp_path):
        node = _make_node(tmp_path)
        # Eliminar el archivo de contexto creado en initialize
        ctx_path = tmp_path / "context.md"
        ctx_path.unlink(missing_ok=True)
        app = create_app(node=node)
        client = TestClient(app)
        resp = client.get("/api/context")
        assert resp.status_code == 200
        assert resp.json()["content"] == ""

    def test_post_context_updates_file(self, tmp_path):
        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app)
        new_content = "## Nuevo contexto\n\nInfo actualizada."
        resp = client.post("/api/context", json={"content": new_content})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert node.store.read_context() == new_content

    def test_post_context_without_content_returns_400(self, tmp_path):
        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app)
        resp = client.post("/api/context", json={"other_field": "value"})
        assert resp.status_code == 400

    def test_post_context_with_invalid_json_returns_400(self, tmp_path):
        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app)
        resp = client.post(
            "/api/context",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_get_patterns_returns_list(self, tmp_path):
        node = _make_node(tmp_path)
        node.store.write_patterns([{"id": "p1", "description": "Patrón de concisión"}])
        app = create_app(node=node)
        client = TestClient(app)
        resp = client.get("/api/patterns")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["id"] == "p1"


# ------------------------------------------------------------------
# C — TestGetRecentThreads
# ------------------------------------------------------------------

class TestGetRecentThreads:
    def test_returns_empty_list_when_no_threads(self, tmp_path):
        node = _make_node(tmp_path)
        result = node.get_recent_threads()
        assert result == []

    def test_returns_metadata_for_each_thread(self, tmp_path):
        node = _make_node(tmp_path)
        _write_thread(node.store, "t1", [
            {
                "thread_id": "t1",
                "from_did": "did:wba:x.com:alice",
                "content": "Mensaje de prueba",
                "status": "pending_human_review",
                "timestamp": "2026-02-22T10:00:00+00:00",
            }
        ])
        result = node.get_recent_threads()
        assert len(result) == 1
        r = result[0]
        assert r["thread_id"] == "t1"
        assert r["from_did"] == "did:wba:x.com:alice"
        assert r["last_message"] == "Mensaje de prueba"
        assert r["message_count"] == 1
        assert r["status"] == "pending_human_review"

    def test_sorts_by_timestamp_desc(self, tmp_path):
        node = _make_node(tmp_path)
        _write_thread(node.store, "old-thread", [
            {"thread_id": "old-thread", "from_did": "did:wba:x.com:a", "content": "Viejo",
             "status": "answered", "timestamp": "2026-02-20T10:00:00+00:00"}
        ])
        _write_thread(node.store, "new-thread", [
            {"thread_id": "new-thread", "from_did": "did:wba:x.com:b", "content": "Nuevo",
             "status": "pending_human_review", "timestamp": "2026-02-22T10:00:00+00:00"}
        ])
        result = node.get_recent_threads()
        assert result[0]["thread_id"] == "new-thread"
        assert result[1]["thread_id"] == "old-thread"

    def test_limits_result(self, tmp_path):
        node = _make_node(tmp_path)
        for i in range(5):
            _write_thread(node.store, f"thread-{i}", [
                {"thread_id": f"thread-{i}", "from_did": "did:wba:x.com:a",
                 "content": f"Msg {i}", "status": "answered",
                 "timestamp": f"2026-02-{i+10:02d}T10:00:00+00:00"}
            ])
        result = node.get_recent_threads(limit=3)
        assert len(result) == 3

    def test_truncates_last_message_to_80_chars(self, tmp_path):
        node = _make_node(tmp_path)
        long_content = "A" * 200
        _write_thread(node.store, "long-thread", [
            {"thread_id": "long-thread", "from_did": "did:wba:x.com:a",
             "content": long_content, "status": "answered",
             "timestamp": "2026-02-22T10:00:00+00:00"}
        ])
        result = node.get_recent_threads()
        assert len(result[0]["last_message"]) == 80

    def test_skips_empty_threads(self, tmp_path):
        node = _make_node(tmp_path)
        # Escribir un thread vacío (no debería aparecer en resultados)
        node.store.write_thread("empty-thread", [])
        result = node.get_recent_threads()
        assert all(t["thread_id"] != "empty-thread" for t in result)


# ------------------------------------------------------------------
# D — TestTypingIndicator
# ------------------------------------------------------------------

class TestTypingIndicator:
    @pytest.mark.asyncio
    async def test_handle_inbound_broadcasts_agent_thinking(self, tmp_path):
        """_handle_inbound debe emitir agent_thinking antes de llamar engine.generate."""
        from esense.core.node import EsenseNode

        node = EsenseNode.__new__(EsenseNode)
        store = MagicMock()
        store.read_thread.return_value = []
        store.write_thread.return_value = None
        node.store = store

        identity = MagicMock()
        identity.did = "did:wba:localhost:testnode"
        node.identity = identity

        engine = MagicMock()
        engine.generate = AsyncMock(return_value="Respuesta propuesta")
        node.engine = engine

        queue = MagicMock()
        queue.approve = AsyncMock()
        node.queue = queue

        peers = MagicMock()
        peers.record_interaction = MagicMock()
        node.peers = peers

        broadcast_calls = []

        async def mock_broadcast(event_type, data):
            broadcast_calls.append((event_type, data))

        with patch("esense.interface.ws.ws_manager") as mock_ws:
            mock_ws.broadcast = mock_broadcast
            message = {
                "thread_id": "test-thread-123",
                "from_did": "did:wba:other.com:bob",
                "content": "Hola nodo",
                "type": "thread_message",
                "status": "pending_human_review",
            }
            await EsenseNode._handle_inbound(node, message)

        # Verificar que agent_thinking fue el primer broadcast
        assert len(broadcast_calls) >= 2
        assert broadcast_calls[0][0] == "agent_thinking"
        assert broadcast_calls[0][1]["thread_id"] == "test-thread-123"

        # Verificar que engine.generate fue llamado
        engine.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_thinking_emitted_before_generate(self, tmp_path):
        """agent_thinking debe aparecer antes del broadcast de review_ready."""
        from esense.core.node import EsenseNode

        node = EsenseNode.__new__(EsenseNode)
        store = MagicMock()
        store.read_thread.return_value = []
        store.write_thread.return_value = None
        node.store = store

        identity = MagicMock()
        identity.did = "did:wba:localhost:testnode"
        node.identity = identity

        engine = MagicMock()
        engine.generate = AsyncMock(return_value="Propuesta")
        node.engine = engine

        queue = MagicMock()
        queue.approve = AsyncMock()
        node.queue = queue

        peers = MagicMock()
        peers.record_interaction = MagicMock()
        node.peers = peers

        call_order = []

        async def mock_broadcast(event_type, data):
            call_order.append(event_type)

        async def mock_generate(**kwargs):
            call_order.append("generate_called")
            return "Propuesta"

        engine.generate = mock_generate

        with patch("esense.interface.ws.ws_manager") as mock_ws:
            mock_ws.broadcast = mock_broadcast
            message = {
                "thread_id": "order-test",
                "from_did": "did:wba:other.com:carol",
                "content": "Test orden",
                "type": "thread_message",
                "status": "pending_human_review",
            }
            await EsenseNode._handle_inbound(node, message)

        # agent_thinking debe preceder a generate_called
        thinking_idx = call_order.index("agent_thinking")
        generate_idx = call_order.index("generate_called")
        assert thinking_idx < generate_idx
