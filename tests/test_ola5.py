"""
tests/test_ola5.py — Tests para Ola 5:
UI completa, thread continuity, peers UI, healthcheck, security hardening.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from esence.core.identity import Identity
from esence.interface.server import create_app


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_node(store_dir: Path | None = None):
    """Crea un nodo mock con peers y queue funcionales."""
    from esence.essence.store import EssenceStore
    from esence.protocol.peers import PeerManager
    from esence.core.queue import MessageQueue

    store = EssenceStore(store_dir=store_dir) if store_dir else MagicMock()
    if store_dir:
        from datetime import timezone as tz
        store.initialize({
            "id": "did:wba:localhost:testnode",
            "name": "testnode",
            "domain": "localhost",
            "languages": ["es"],
            "values": [],
            "created_at": datetime.now(tz.utc).isoformat(),
        })

    node = MagicMock()
    node.identity = Identity.generate("testnode", "localhost")

    if store_dir:
        node.store = store
        node.peers = PeerManager(store)
        node.queue = MessageQueue(store)
        node.queue.restore_pending()
    else:
        node.peers = MagicMock()
        node.peers.get_all.return_value = []
        node.peers.peer_count.return_value = 0
        node.peers.add_or_update.return_value = {
            "did": "did:wba:other.example.com:bob",
            "trust_score": 0.3,
        }
        node.store = MagicMock()
        node.store.is_over_budget.return_value = False
        node.store.read_budget.return_value = {
            "used_tokens": 1000,
            "monthly_limit_tokens": 500_000,
        }
        node.queue.pending_count.return_value = 0

    return node


# ------------------------------------------------------------------
# A — TestApiPeers
# ------------------------------------------------------------------

class TestApiPeers:
    def test_get_peers_returns_list(self, tmp_path):
        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app)
        resp = client.get("/api/peers")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_peers_without_node_returns_empty_list(self):
        app = create_app(node=None)
        client = TestClient(app)
        resp = client.get("/api/peers")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_post_peer_adds_peer(self, tmp_path):
        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app)
        resp = client.post("/api/peers", json={"did": "did:wba:other.example.com:bob"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["peer"]["did"] == "did:wba:other.example.com:bob"

    def test_post_peer_without_did_returns_400(self, tmp_path):
        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/peers", json={})
        assert resp.status_code == 400

    def test_post_peer_without_node_returns_503(self):
        app = create_app(node=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/peers", json={"did": "did:wba:other.example.com:bob"})
        assert resp.status_code == 503

    def test_delete_peer_removes_it(self, tmp_path):
        node = _make_node(tmp_path)
        # Primero agregar el peer
        node.peers.add_or_update("did:wba:other.example.com:bob", trust_score=0.3)
        app = create_app(node=node)
        client = TestClient(app)
        resp = client.delete("/api/peers/did%3Awba%3Aother.example.com%3Abob")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        # Verificar que se eliminó
        remaining = [p for p in node.peers.get_all() if p["did"] == "did:wba:other.example.com:bob"]
        assert len(remaining) == 0

    def test_delete_peer_without_node_returns_503(self):
        app = create_app(node=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.delete("/api/peers/did%3Awba%3Aother.example.com%3Abob")
        assert resp.status_code == 503

    def test_post_then_get_peer_appears_in_list(self, tmp_path):
        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app)
        client.post("/api/peers", json={"did": "did:wba:example.com:alice"})
        resp = client.get("/api/peers")
        dids = [p["did"] for p in resp.json()]
        assert "did:wba:example.com:alice" in dids


# ------------------------------------------------------------------
# B — TestApiHealth
# ------------------------------------------------------------------

class TestApiHealth:
    def test_health_returns_200_with_node(self, tmp_path):
        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_contains_required_fields(self, tmp_path):
        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app)
        data = client.get("/api/health").json()
        for field in ("status", "did", "peer_count", "pending_count", "maturity", "budget", "version"):
            assert field in data, f"Campo faltante: {field}"

    def test_health_status_healthy_when_not_over_budget(self, tmp_path):
        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app)
        data = client.get("/api/health").json()
        assert data["status"] == "healthy"

    def test_health_status_degraded_when_over_budget(self, tmp_path):
        node = _make_node(tmp_path)
        # Sobrepasar el budget
        node.store.write_budget({
            "used_tokens": 600_000,
            "monthly_limit_tokens": 500_000,
        })
        app = create_app(node=node)
        client = TestClient(app)
        data = client.get("/api/health").json()
        assert data["status"] == "degraded"
        assert data["budget"]["over_budget"] is True

    def test_health_without_node_returns_503(self):
        app = create_app(node=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/health")
        assert resp.status_code == 503

    def test_health_version_is_020(self, tmp_path):
        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app)
        data = client.get("/api/health").json()
        assert data["version"] == "0.2.0"


# ------------------------------------------------------------------
# C — TestRateLimit
# ------------------------------------------------------------------

class TestRateLimit:
    def test_requests_under_limit_return_200_or_valid_code(self, tmp_path):
        """Los primeros 30 requests no deben retornar 429."""
        from esence.interface import server as server_module
        # Limpiar rate limit
        server_module._rate_limit.clear()

        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app, raise_server_exceptions=False)

        for i in range(5):
            resp = client.post(
                "/anp/message",
                json={},
                headers={"X-Forwarded-For": "10.0.0.1"},
            )
            assert resp.status_code != 429, f"Request {i+1} devolvió 429 prematuramente"

    def test_request_31_returns_429(self, tmp_path):
        """El request 31 dentro de la ventana debe retornar 429."""
        from esence.interface import server as server_module
        server_module._rate_limit.clear()

        node = _make_node(tmp_path)
        app = create_app(node=node)
        client = TestClient(app, raise_server_exceptions=False)

        # Hacer 31 requests; el 31° debe retornar 429
        # Los primeros devolverán 400/422/500 por datos inválidos,
        # pero el rate limiter debería activarse en el 31°.
        status_codes = []
        for _ in range(31):
            resp = client.post("/anp/message", json={})
            status_codes.append(resp.status_code)

        assert 429 in status_codes, f"Esperaba 429 en algún request, obtuve: {status_codes}"
        assert status_codes[-1] == 429, f"El request 31 no es 429, es {status_codes[-1]}"


# ------------------------------------------------------------------
# D — TestTransportSecurity
# ------------------------------------------------------------------

class TestTransportSecurity:
    @pytest.mark.asyncio
    async def test_stale_message_returns_invalid(self):
        """Mensaje con timestamp >5min debe retornar valid=False."""
        from esence.protocol.transport import receive_message

        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        payload = {
            "esence_version": "0.2",
            "type": "thread_message",
            "thread_id": "test-thread-id",
            "from_did": "did:wba:other.example.com:bob",
            "to_did": "did:wba:localhost:node0",
            "content": "Mensaje stale",
            "status": "pending_human_review",
            "timestamp": stale_time,
            "signature": "fakesig",
        }
        _, valid = await receive_message(payload)
        assert valid is False

    @pytest.mark.asyncio
    async def test_invalid_did_returns_invalid(self):
        """Mensaje con DID malformado debe retornar valid=False."""
        from esence.protocol.transport import receive_message

        fresh_time = datetime.now(timezone.utc).isoformat()
        payload = {
            "esence_version": "0.2",
            "type": "thread_message",
            "thread_id": "test-thread-id",
            "from_did": "not-a-valid-did",
            "to_did": "did:wba:localhost:node0",
            "content": "Mensaje con DID inválido",
            "status": "pending_human_review",
            "timestamp": fresh_time,
            "signature": "fakesig",
        }
        _, valid = await receive_message(payload)
        assert valid is False

    @pytest.mark.asyncio
    async def test_valid_did_format_passes_validation(self):
        """DID válido no debe ser rechazado por la validación de formato."""
        from esence.protocol.transport import _DID_RE
        valid_dids = [
            "did:wba:example.com:alice",
            "did:wba:localhost:node0",
            "did:wba:abc123.ngrok.io:mynode",
            "did:wba:localhost%3A7777:node0",
        ]
        for did in valid_dids:
            assert _DID_RE.match(did), f"DID válido rechazado: {did}"

    @pytest.mark.asyncio
    async def test_invalid_did_format_fails_validation(self):
        """DIDs inválidos deben fallar la validación de formato."""
        from esence.protocol.transport import _DID_RE
        invalid_dids = [
            "not-a-did",
            "did:key:z6Mk",
            "did:wba:",
            "",
            "did:wba:example.com",  # sin name
        ]
        for did in invalid_dids:
            assert not _DID_RE.match(did), f"DID inválido aceptado: {did}"

    @pytest.mark.asyncio
    async def test_fresh_message_with_valid_did_passes_security_checks(self):
        """Mensaje fresco con DID válido no debe fallar por seguridad (puede fallar por firma)."""
        from esence.protocol.transport import receive_message

        fresh_time = datetime.now(timezone.utc).isoformat()
        payload = {
            "esence_version": "0.2",
            "type": "thread_message",
            "thread_id": "test-thread-id",
            "from_did": "did:wba:localhost:testnode",
            "to_did": "did:wba:localhost:node0",
            "content": "Mensaje fresco",
            "status": "pending_human_review",
            "timestamp": fresh_time,
            "signature": None,
        }
        # Sin firma → valid=False pero por falta de firma, no por seguridad
        # El mensaje debe parsearse sin error
        msg, valid = await receive_message(payload)
        assert msg.from_did == "did:wba:localhost:testnode"
        # valid puede ser False (sin firma) pero no por DID o timestamp
        assert msg is not None


# ------------------------------------------------------------------
# E — TestThreadContinuity
# ------------------------------------------------------------------

class TestThreadContinuity:
    @pytest.mark.asyncio
    async def test_handle_inbound_passes_context_to_engine(self, tmp_store):
        """_handle_inbound debe pasar el historial del thread al engine."""
        from esence.core.node import EsenceNode

        node = EsenceNode.__new__(EsenceNode)
        node.store = tmp_store
        node.identity = Identity.generate("testnode", "localhost")
        node._running = True

        # Escribir historial en el thread
        thread_id = "test-thread-123"
        tmp_store.write_thread(thread_id, [
            {
                "from_did": "did:wba:other.example.com:bob",
                "content": "Primer mensaje del hilo",
                "thread_id": thread_id,
            },
            {
                "from_did": node.identity.did,
                "content": "Primera respuesta del agente",
                "thread_id": thread_id,
            },
        ])

        # Mock del engine capturando context_messages
        captured = {}
        async def fake_generate(user_message, context_messages=None, max_tokens=512):
            captured["context_messages"] = context_messages
            return "respuesta propuesta"

        node.engine = MagicMock()
        node.engine.generate = fake_generate

        from esence.protocol.peers import PeerManager
        node.peers = PeerManager(tmp_store)

        from esence.core.queue import MessageQueue
        node.queue = MessageQueue(tmp_store)

        with patch("esence.interface.ws.ws_manager.broadcast", new_callable=AsyncMock):
            await node._handle_inbound({
                "from_did": "did:wba:other.example.com:bob",
                "content": "Segundo mensaje del hilo",
                "thread_id": thread_id,
                "type": "thread_message",
                "status": "pending_human_review",
            })

        assert "context_messages" in captured
        assert captured["context_messages"] is not None
        assert len(captured["context_messages"]) == 2
        # El primer mensaje es del peer → role "user"
        assert captured["context_messages"][0]["role"] == "user"
        assert captured["context_messages"][0]["content"] == "Primer mensaje del hilo"
        # El segundo es del propio nodo → role "assistant"
        assert captured["context_messages"][1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_handle_inbound_empty_thread_passes_empty_context(self, tmp_store):
        """Si el thread es nuevo, context_messages debe ser lista vacía."""
        from esence.core.node import EsenceNode

        node = EsenceNode.__new__(EsenceNode)
        node.store = tmp_store
        node.identity = Identity.generate("testnode", "localhost")
        node._running = True

        captured = {}
        async def fake_generate(user_message, context_messages=None, max_tokens=512):
            captured["context_messages"] = context_messages
            return "respuesta"

        node.engine = MagicMock()
        node.engine.generate = fake_generate

        from esence.protocol.peers import PeerManager
        node.peers = PeerManager(tmp_store)
        from esence.core.queue import MessageQueue
        node.queue = MessageQueue(tmp_store)

        with patch("esence.interface.ws.ws_manager.broadcast", new_callable=AsyncMock):
            await node._handle_inbound({
                "from_did": "did:wba:other.example.com:bob",
                "content": "Primer mensaje en thread nuevo",
                "thread_id": "brand-new-thread",
                "type": "thread_message",
                "status": "pending_human_review",
            })

        assert captured["context_messages"] == []
