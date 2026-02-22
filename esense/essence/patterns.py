"""
esense/essence/patterns.py — Extracción automática de patrones desde corrections.log
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from esense.essence.engine import EssenceEngine
    from esense.essence.store import EssenceStore

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
Analizá las siguientes correcciones que el dueño del nodo hizo a las respuestas del agente.
Cada corrección tiene: 'original' (lo que el agente propuso) y 'edited' (lo que el dueño aprobó).

Correcciones:
{corrections_json}

Extraé patrones de razonamiento concretos. Un patrón captura UNA forma consistente en que \
el dueño ajusta las respuestas: su tono preferido, nivel de detalle, valores que enfatiza, \
temas que evita, etc.

Respondé SOLO con un JSON array de objetos con esta estructura exacta:
[
  {{
    "description": "descripción breve del patrón (1 oración)",
    "examples": ["ejemplo de original → edited", ...],
    "confidence": 0.0-1.0
  }}
]

Si no encontrás patrones claros, respondé con [].
No incluyas explicaciones fuera del JSON.
"""


async def extract_patterns(store: "EssenceStore", engine: "EssenceEngine", last_n: int = 5) -> int:
    """
    Analiza las últimas N correcciones y extrae patrones de razonamiento.

    Retorna la cantidad de patrones nuevos agregados.
    """
    corrections = store.read_corrections()
    if not corrections:
        return 0

    recent = corrections[-last_n:]
    # Solo analizar correcciones donde hubo edición real
    meaningful = [
        c for c in recent
        if c.get("edited") and c.get("original") and c["edited"] != c["original"]
    ]

    if not meaningful:
        logger.info("Sin correcciones con ediciones reales para extraer patrones")
        return 0

    corrections_json = json.dumps(
        [{"original": c["original"], "edited": c["edited"]} for c in meaningful],
        ensure_ascii=False,
        indent=2,
    )

    prompt = _EXTRACTION_PROMPT.format(corrections_json=corrections_json)

    try:
        raw = await engine.generate(
            user_message=prompt,
            max_tokens=1024,
        )
    except Exception as e:
        logger.error(f"Error llamando al engine para extraer patrones: {e}")
        return 0

    # Intentar parsear el JSON de la respuesta
    try:
        # Limpiar posibles markdown code fences
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        new_patterns = json.loads(text)
        if not isinstance(new_patterns, list):
            logger.warning("La respuesta de extracción no es una lista JSON")
            return 0
    except json.JSONDecodeError as e:
        logger.warning(f"No se pudo parsear la respuesta de extracción de patrones: {e}")
        return 0

    if not new_patterns:
        return 0

    # Evitar duplicados por description
    existing_patterns = store.read_patterns()
    existing_descriptions = {p.get("description", "").lower() for p in existing_patterns}

    added = 0
    now = datetime.now(timezone.utc).isoformat()
    for pattern in new_patterns:
        desc = pattern.get("description", "").lower()
        if not desc or desc in existing_descriptions:
            continue
        pattern["extracted_at"] = now
        pattern.setdefault("confidence", 0.5)
        pattern.setdefault("examples", [])
        existing_patterns.append(pattern)
        existing_descriptions.add(desc)
        added += 1

    if added:
        store.write_patterns(existing_patterns)
        logger.info(f"Patrones extraídos: {added} nuevos (total: {len(existing_patterns)})")

    return added
