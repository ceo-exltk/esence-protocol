"""
tests/test_store.py — Tests del EssenceStore (CRUD, corrections, threads, budget reset)
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from esence.essence.store import EssenceStore


def test_initialize_creates_files(tmp_store: EssenceStore):
    """initialize() crea todos los archivos necesarios."""
    assert (tmp_store.dir / "identity.json").exists()
    assert (tmp_store.dir / "patterns.json").exists()
    assert (tmp_store.dir / "context.md").exists()
    assert (tmp_store.dir / "corrections.log").exists()
    assert (tmp_store.dir / "peers.json").exists()
    assert (tmp_store.dir / "budget.json").exists()
    assert (tmp_store.dir / "threads").is_dir()


def test_read_write_identity(tmp_store: EssenceStore):
    data = {"id": "did:wba:localhost:test", "name": "test"}
    tmp_store.write_identity(data)
    assert tmp_store.read_identity() == data


def test_read_write_patterns(tmp_store: EssenceStore):
    patterns = [{"description": "patrón 1", "confidence": 0.8, "examples": []}]
    tmp_store.write_patterns(patterns)
    loaded = tmp_store.read_patterns()
    assert len(loaded) == 1
    assert loaded[0]["description"] == "patrón 1"


def test_add_pattern_appends(tmp_store: EssenceStore):
    tmp_store.write_patterns([])
    tmp_store.add_pattern({"description": "patrón A"})
    tmp_store.add_pattern({"description": "patrón B"})
    patterns = tmp_store.read_patterns()
    assert len(patterns) == 2


def test_corrections_log_jsonl(tmp_store: EssenceStore):
    c1 = {"original": "hola", "edited": "hola mundo", "thread_id": "t1", "from_did": "did:wba:test"}
    c2 = {"original": "x", "edited": "x", "thread_id": "t2", "from_did": "did:wba:test"}
    tmp_store.append_correction(c1)
    tmp_store.append_correction(c2)

    corrections = tmp_store.read_corrections()
    assert len(corrections) == 2
    assert corrections[0]["original"] == "hola"
    assert corrections[1]["original"] == "x"
    # Verificar que se añadió timestamp
    assert "timestamp" in corrections[0]


def test_thread_append_and_read(tmp_store: EssenceStore):
    msg1 = {"content": "hola", "thread_id": "abc"}
    msg2 = {"content": "mundo", "thread_id": "abc"}
    tmp_store.append_to_thread("abc", msg1)
    tmp_store.append_to_thread("abc", msg2)
    messages = tmp_store.read_thread("abc")
    assert len(messages) == 2
    assert messages[0]["content"] == "hola"


def test_list_threads(tmp_store: EssenceStore):
    tmp_store.append_to_thread("thread-1", {"content": "a"})
    tmp_store.append_to_thread("thread-2", {"content": "b"})
    threads = tmp_store.list_threads()
    assert "thread-1" in threads
    assert "thread-2" in threads


def test_upsert_peer(tmp_store: EssenceStore):
    tmp_store.upsert_peer({"did": "did:wba:localhost:peer1", "trust_score": 0.5})
    peers = tmp_store.read_peers()
    assert len(peers) == 1
    # Upsert actualiza
    tmp_store.upsert_peer({"did": "did:wba:localhost:peer1", "trust_score": 0.8})
    peers = tmp_store.read_peers()
    assert len(peers) == 1
    assert peers[0]["trust_score"] == 0.8


def test_budget_read_write(tmp_store: EssenceStore):
    budget = tmp_store.read_budget()
    assert "monthly_limit_tokens" in budget
    assert "used_tokens" in budget
    assert "autonomy_threshold" in budget
    assert budget["autonomy_threshold"] == 0.6


def test_record_usage(tmp_store: EssenceStore):
    initial = tmp_store.read_budget().get("used_tokens", 0)
    tmp_store.record_usage(1000)
    tmp_store.record_usage(500)
    budget = tmp_store.read_budget()
    assert budget["used_tokens"] == initial + 1500
    assert budget["calls_total"] >= 2


def test_budget_monthly_reset(tmp_store: EssenceStore):
    """Si last_reset es del mes pasado, el budget se resetea al leer."""
    import json

    # Setear last_reset al mes pasado
    budget = tmp_store.read_budget()
    budget["used_tokens"] = 99999
    budget["calls_total"] = 100
    # Fecha en el pasado (año diferente para ser seguros)
    budget["last_reset"] = "2020-01-01T00:00:00+00:00"
    tmp_store.write_budget(budget)

    # is_over_budget() debe resetear y retornar False (usado_tokens = 0 < límite)
    result = tmp_store.is_over_budget()
    assert result is False

    refreshed = tmp_store.read_budget()
    assert refreshed["used_tokens"] == 0
    assert refreshed["calls_total"] == 0


def test_is_over_budget_true(tmp_store: EssenceStore):
    budget = tmp_store.read_budget()
    budget["used_tokens"] = budget["monthly_limit_tokens"]
    tmp_store.write_budget(budget)
    assert tmp_store.is_over_budget() is True


def test_context_read_write(tmp_store: EssenceStore):
    tmp_store.write_context("# Contexto\nContenido de prueba")
    content = tmp_store.read_context()
    assert "Contenido de prueba" in content


def test_append_context(tmp_store: EssenceStore):
    tmp_store.write_context("# Base\n")
    tmp_store.append_context("Nueva sección", "contenido nuevo")
    content = tmp_store.read_context()
    assert "Nueva sección" in content
    assert "contenido nuevo" in content
