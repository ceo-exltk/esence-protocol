"""
esence/essence/maturity.py — Calcula el essence_maturity score (0.0 – 1.0)

El score refleja cuánto ha "aprendido" el agente sobre su dueño:
- Cantidad de correcciones en corrections.log
- Cantidad de patrones en patterns.json
- Longitud del contexto acumulado en context.md
"""
from __future__ import annotations

import math
from pathlib import Path

from esence.config import config
from esence.essence.store import EssenceStore


def _sigmoid_score(value: float, midpoint: float) -> float:
    """Mapea un valor positivo a (0, 1) con punto medio configurable."""
    return 1 / (1 + math.exp(-(value - midpoint) / (midpoint / 2)))


def calculate_maturity(store: EssenceStore | None = None) -> float:
    """
    Calcula el essence_maturity como promedio ponderado de tres factores.

    Retorna un float en [0.0, 1.0].
    """
    store = store or EssenceStore()

    # Factor 1: Correcciones (peso 0.4)
    # Punto medio: 50 correcciones → 0.5
    corrections = store.read_corrections()
    corrections_score = _sigmoid_score(len(corrections), midpoint=50)

    # Factor 2: Patrones extraídos (peso 0.35)
    # Punto medio: 20 patrones → 0.5
    patterns = store.read_patterns()
    patterns_score = _sigmoid_score(len(patterns), midpoint=20)

    # Factor 3: Longitud del contexto en palabras (peso 0.25)
    # Punto medio: 500 palabras → 0.5
    context = store.read_context()
    word_count = len(context.split())
    context_score = _sigmoid_score(word_count, midpoint=500)

    # Promedio ponderado
    maturity = (
        corrections_score * 0.40
        + patterns_score * 0.35
        + context_score * 0.25
    )

    return round(min(max(maturity, 0.0), 1.0), 4)


def maturity_label(score: float) -> str:
    """Etiqueta descriptiva del score."""
    if score < 0.2:
        return "nascent"
    if score < 0.4:
        return "emerging"
    if score < 0.6:
        return "developing"
    if score < 0.8:
        return "established"
    return "mature"
