"""
tests/test_maturity.py — Tests del essence maturity score
"""
from __future__ import annotations

import pytest

from esense.essence.maturity import calculate_maturity, maturity_label
from esense.essence.store import EssenceStore


def test_maturity_zero_with_empty_store(tmp_store: EssenceStore):
    """Store vacío → score muy bajo (nascent)."""
    score = calculate_maturity(tmp_store)
    assert 0.0 <= score < 0.3
    assert maturity_label(score) == "nascent"


def test_maturity_increases_with_corrections(tmp_store: EssenceStore):
    """Agregar correcciones aumenta el score."""
    score_before = calculate_maturity(tmp_store)

    for i in range(5):
        tmp_store.append_correction({
            "original": f"original {i}",
            "edited": f"editado {i}",
            "thread_id": f"t{i}",
            "from_did": "did:wba:localhost:peer",
        })

    score_after = calculate_maturity(tmp_store)
    assert score_after > score_before


def test_maturity_increases_with_patterns(tmp_store: EssenceStore):
    """Agregar patrones aumenta el score."""
    score_before = calculate_maturity(tmp_store)

    for i in range(5):
        tmp_store.add_pattern({"description": f"patrón {i}", "confidence": 0.8})

    score_after = calculate_maturity(tmp_store)
    assert score_after > score_before


def test_maturity_with_many_corrections(tmp_store: EssenceStore):
    """50 correcciones → score cercano al punto medio (0.5 en ese factor)."""
    for i in range(50):
        tmp_store.append_correction({
            "original": f"orig {i}",
            "edited": f"edit {i}",
            "thread_id": f"t{i}",
            "from_did": "did:wba:localhost:peer",
        })
    score = calculate_maturity(tmp_store)
    # Factor correcciones en punto medio (0.5) * 0.4 = 0.2
    # Con patrones y contexto vacíos, score total sería ~0.2 (nascent/emerging)
    assert score > 0.1


def test_maturity_score_bounds(tmp_store: EssenceStore):
    """El score siempre está en [0.0, 1.0]."""
    score = calculate_maturity(tmp_store)
    assert 0.0 <= score <= 1.0


def test_maturity_label_boundaries():
    assert maturity_label(0.0) == "nascent"
    assert maturity_label(0.19) == "nascent"
    assert maturity_label(0.2) == "emerging"
    assert maturity_label(0.39) == "emerging"
    assert maturity_label(0.4) == "developing"
    assert maturity_label(0.59) == "developing"
    assert maturity_label(0.6) == "established"
    assert maturity_label(0.79) == "established"
    assert maturity_label(0.8) == "mature"
    assert maturity_label(1.0) == "mature"
