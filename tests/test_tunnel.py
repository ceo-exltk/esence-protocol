"""
tests/test_tunnel.py — Tests para auto-ngrok tunnel detection (Ola 7)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from esense.core.node import EsenseNode


@pytest.fixture
def node(tmp_store):
    n = EsenseNode()
    n.store = tmp_store
    return n


# ---------------------------------------------------------------------------
# TestDetectNgrokTunnel
# ---------------------------------------------------------------------------

class TestDetectNgrokTunnel:
    @pytest.mark.asyncio
    async def test_returns_url_when_tunnel_found(self, node):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tunnels": [
                {
                    "proto": "https",
                    "public_url": "https://abc.ngrok-free.app",
                    "config": {"addr": "http://localhost:7777"},
                }
            ]
        }
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            url = await node._detect_ngrok_tunnel()

        assert url == "https://abc.ngrok-free.app"

    @pytest.mark.asyncio
    async def test_returns_none_when_ngrok_not_running(self, node):
        import httpx

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            url = await node._detect_ngrok_tunnel()

        assert url is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_tunnel_for_port(self, node):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tunnels": [
                {
                    "proto": "https",
                    "public_url": "https://other.ngrok-free.app",
                    "config": {"addr": "http://localhost:9999"},  # puerto diferente
                }
            ]
        }
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            url = await node._detect_ngrok_tunnel()

        assert url is None


# ---------------------------------------------------------------------------
# TestStartNgrok
# ---------------------------------------------------------------------------

class TestStartNgrok:
    @pytest.mark.asyncio
    async def test_returns_none_when_ngrok_not_installed(self, node):
        with patch("shutil.which", return_value=None):
            url = await node._start_ngrok()

        assert url is None

    @pytest.mark.asyncio
    async def test_returns_url_after_polling(self, node):
        call_count = 0

        async def detect_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                return "https://xyz.ngrok-free.app"
            return None

        with patch("shutil.which", return_value="/usr/local/bin/ngrok"), \
             patch("subprocess.Popen"), \
             patch.object(node, "_detect_ngrok_tunnel", side_effect=detect_side_effect), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            url = await node._start_ngrok()

        assert url == "https://xyz.ngrok-free.app"


# ---------------------------------------------------------------------------
# TestAutoConfigureInStart
# ---------------------------------------------------------------------------

class TestAutoConfigureInStart:
    @pytest.mark.asyncio
    async def test_config_public_url_updated_when_tunnel_found(self, node, tmp_path):
        from esense.config import Config

        original_url = Config.public_url
        Config.public_url = ""  # asegurar sin URL previa

        try:
            detected_url = "https://auto.ngrok-free.app"

            with patch.object(node, "_detect_ngrok_tunnel", AsyncMock(return_value=detected_url)), \
                 patch.object(node, "_start_ngrok", AsyncMock(return_value=None)), \
                 patch.object(node, "_run_http_server", AsyncMock()), \
                 patch.object(node, "_process_inbound_loop", AsyncMock()), \
                 patch.object(node, "_process_outbound_loop", AsyncMock()), \
                 patch.object(node, "_gossip_loop", AsyncMock()), \
                 patch("esense.core.node.config.essence_store_dir", tmp_path), \
                 patch("esense.core.identity.Identity.load_or_generate") as mock_id, \
                 patch("esense.core.node.config.validate", return_value=[]):
                mock_identity = MagicMock()
                mock_identity.did = "did:wba:auto.ngrok-free.app:node0"
                mock_id.return_value = mock_identity

                import asyncio
                await asyncio.gather(node.start(), return_exceptions=True)

            assert Config.public_url == detected_url
        finally:
            Config.public_url = original_url
