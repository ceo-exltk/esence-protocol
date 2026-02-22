"""
tests/conftest.py — Fixtures compartidas para el test suite de Esense
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from esense.core.identity import Identity
from esense.essence.store import EssenceStore


@pytest.fixture
def tmp_store(tmp_path: Path) -> EssenceStore:
    """EssenceStore apuntando a un directorio temporal vacío."""
    store = EssenceStore(store_dir=tmp_path)
    identity_data = {
        "id": "did:wba:localhost:testnode",
        "name": "testnode",
        "domain": "localhost",
        "languages": ["es"],
        "values": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store.initialize(identity_data)
    return store


@pytest.fixture
def test_identity() -> Identity:
    """Identidad Ed25519 generada en memoria para tests."""
    return Identity.generate("testnode", "localhost")


@pytest.fixture
def mock_engine(tmp_store: EssenceStore) -> MagicMock:
    """Engine mockeado que retorna respuestas predecibles."""
    engine = MagicMock()
    engine.store = tmp_store
    engine.generate = AsyncMock(return_value="respuesta mockeada del agente")
    engine.generate_self_response = AsyncMock(return_value="respuesta self mockeada")
    return engine
