"""
tests/test_ola4.py — Tests para Ola 4: conectividad real entre nodos
Cubre: config.effective_domain, config.did, config.did_document_url,
       identity.update_domain, node domain reconciliation, /api/send endpoint
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from esense.core.identity import Identity
from esense.interface.server import create_app


# ------------------------------------------------------------------
# Config — effective_domain, did, did_document_url
# ------------------------------------------------------------------

class TestConfigEffectiveDomain:
    def test_effective_domain_without_public_url(self):
        from esense.config import Config
        with patch.object(Config, "public_url", ""), \
             patch.object(Config, "domain", "localhost"):
            assert Config.effective_domain() == "localhost"

    def test_effective_domain_with_public_url(self):
        from esense.config import Config
        with patch.object(Config, "public_url", "https://abc123.ngrok.io"):
            assert Config.effective_domain() == "abc123.ngrok.io"

    def test_effective_domain_strips_path_from_url(self):
        from esense.config import Config
        with patch.object(Config, "public_url", "https://mi-nodo.example.com/extra"):
            assert Config.effective_domain() == "mi-nodo.example.com"

    def test_did_uses_effective_domain_when_public_url_set(self):
        from esense.config import Config
        with patch.object(Config, "public_url", "https://abc123.ngrok.io"), \
             patch.object(Config, "node_name", "node0"):
            assert Config.did() == "did:wba:abc123.ngrok.io:node0"

    def test_did_uses_local_domain_without_public_url(self):
        from esense.config import Config
        with patch.object(Config, "public_url", ""), \
             patch.object(Config, "domain", "localhost"), \
             patch.object(Config, "node_name", "node0"), \
             patch.object(Config, "port", 7777):
            # Para localhost el DID incluye el puerto URL-encoded
            assert Config.did() == "did:wba:localhost%3A7777:node0"

    def test_did_document_url_with_public_url(self):
        from esense.config import Config
        with patch.object(Config, "public_url", "https://abc123.ngrok.io"):
            url = Config.did_document_url()
            assert url == "https://abc123.ngrok.io/.well-known/did.json"

    def test_did_document_url_with_trailing_slash_in_public_url(self):
        from esense.config import Config
        with patch.object(Config, "public_url", "https://abc123.ngrok.io/"):
            url = Config.did_document_url()
            assert url == "https://abc123.ngrok.io/.well-known/did.json"

    def test_did_document_url_localhost_uses_http_and_port(self):
        from esense.config import Config
        with patch.object(Config, "public_url", ""), \
             patch.object(Config, "domain", "localhost"), \
             patch.object(Config, "port", 7777):
            url = Config.did_document_url()
            assert url == "http://localhost:7777/.well-known/did.json"

    def test_did_document_url_real_domain_uses_https_no_port(self):
        from esense.config import Config
        with patch.object(Config, "public_url", ""), \
             patch.object(Config, "domain", "mi-nodo.example.com"):
            url = Config.did_document_url()
            assert url.startswith("https://mi-nodo.example.com/")
            assert "7777" not in url


# ------------------------------------------------------------------
# Identity — update_domain
# ------------------------------------------------------------------

class TestIdentityUpdateDomain:
    def test_update_domain_changes_did(self, test_identity: Identity):
        test_identity.update_domain("newdomain.example.com")
        assert "newdomain.example.com" in test_identity.did
        assert test_identity.did.startswith("did:wba:newdomain.example.com:")

    def test_update_domain_preserves_node_name(self, test_identity: Identity):
        original_node = test_identity.did.split(":")[-1]
        test_identity.update_domain("newdomain.example.com")
        assert test_identity.did.endswith(f":{original_node}")

    def test_update_domain_preserves_keys(self, test_identity: Identity):
        original_pubkey = test_identity.public_key_b64()
        test_identity.update_domain("newdomain.example.com")
        assert test_identity.public_key_b64() == original_pubkey

    def test_update_domain_writes_did_json(self, test_identity: Identity, tmp_path: Path):
        test_identity.update_domain("newdomain.example.com", store_dir=tmp_path)
        did_doc = json.loads((tmp_path / "did.json").read_text())
        assert did_doc["id"] == test_identity.did
        assert "newdomain.example.com" in did_doc["id"]

    def test_update_domain_did_json_keeps_same_public_key(
        self, test_identity: Identity, tmp_path: Path
    ):
        original_pubkey = test_identity.public_key_b64()
        test_identity.update_domain("newdomain.example.com", store_dir=tmp_path)
        did_doc = json.loads((tmp_path / "did.json").read_text())
        vm = did_doc["verificationMethod"][0]
        # publicKeyMultibase tiene prefijo "z" seguido del b64
        assert original_pubkey in vm["publicKeyMultibase"]

    def test_update_domain_twice(self, test_identity: Identity, tmp_path: Path):
        test_identity.update_domain("first.example.com", store_dir=tmp_path)
        test_identity.update_domain("second.example.com", store_dir=tmp_path)
        assert "second.example.com" in test_identity.did
        did_doc = json.loads((tmp_path / "did.json").read_text())
        assert "second.example.com" in did_doc["id"]

    def test_sign_verify_still_works_after_update_domain(self, test_identity: Identity):
        test_identity.update_domain("newdomain.example.com")
        payload = b"test payload after domain update"
        sig = test_identity.sign(payload)
        assert test_identity.verify(payload, sig)


# ------------------------------------------------------------------
# /api/send endpoint
# ------------------------------------------------------------------

class TestApiSendEndpoint:
    def _make_app(self, send_success: bool = True):
        node = MagicMock()
        node.identity = Identity.generate("testnode", "localhost")
        mock_send = AsyncMock(return_value=send_success)
        app = create_app(node=node)
        return app, mock_send

    def test_send_returns_sent_on_success(self):
        node = MagicMock()
        node.identity = Identity.generate("testnode", "localhost")
        app = create_app(node=node)
        with patch("esense.protocol.transport.send_message", new_callable=AsyncMock, return_value=True):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post("/api/send", json={
                "to_did": "did:wba:other.example.com:bob",
                "content": "Hola bob",
            })
        assert resp.status_code == 200
        assert resp.json()["status"] == "sent"

    def test_send_returns_failed_on_transport_error(self):
        node = MagicMock()
        node.identity = Identity.generate("testnode", "localhost")
        app = create_app(node=node)
        with patch("esense.protocol.transport.send_message", new_callable=AsyncMock, return_value=False):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post("/api/send", json={
                "to_did": "did:wba:other.example.com:bob",
                "content": "Hola bob",
            })
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"

    def test_send_missing_to_did_returns_400(self):
        node = MagicMock()
        node.identity = Identity.generate("testnode", "localhost")
        app = create_app(node=node)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/send", json={"content": "Hola"})
        assert resp.status_code == 400

    def test_send_missing_content_returns_400(self):
        node = MagicMock()
        node.identity = Identity.generate("testnode", "localhost")
        app = create_app(node=node)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/send", json={"to_did": "did:wba:other.example.com:bob"})
        assert resp.status_code == 400

    def test_send_without_node_returns_503(self):
        app = create_app(node=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/send", json={
            "to_did": "did:wba:other.example.com:bob",
            "content": "Hola",
        })
        assert resp.status_code == 503

    def test_send_uses_node_identity_did_as_from_did(self):
        node = MagicMock()
        node.identity = Identity.generate("testnode", "localhost")
        expected_from = node.identity.did
        app = create_app(node=node)
        captured = {}

        async def fake_send(msg, identity):
            captured["from_did"] = msg.from_did
            return True

        with patch("esense.protocol.transport.send_message", side_effect=fake_send):
            client = TestClient(app, raise_server_exceptions=True)
            client.post("/api/send", json={
                "to_did": "did:wba:other.example.com:bob",
                "content": "Hola",
            })
        assert captured["from_did"] == expected_from
