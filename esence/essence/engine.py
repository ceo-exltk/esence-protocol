"""
esence/essence/engine.py — Motor de generación de respuestas

Construye el system prompt desde el essence store y delega la generación
al provider configurado (anthropic, claude_code, ollama, openai).
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from esence.config import config
from esence.essence.maturity import calculate_maturity, maturity_label
from esence.essence.store import EssenceStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """Sos el agente digital de {name} en la red Esence.

## Tu identidad
DID: {did}
Nombre del nodo: {name}
Dominio: {domain}
Essence maturity: {maturity_score} ({maturity_label})

## Tu esencia
{context}

## Patrones de razonamiento conocidos
{patterns}

## Principios que guían tu comportamiento
- Representás a {name}, no a Anthropic ni a ninguna empresa.
- Respondés en primera persona como agente de {name}.
- Antes de comprometerte a algo importante, consultás con {name}.
- Sos asincrónico: no te apurás, priorizás respuestas reflexivas.
- No inventás información sobre {name}. Si no sabés, decís que no sabés.
- Todo lo que salga de vos lleva tu firma Ed25519.

## Instrucción actual
{instruction}
"""


class EssenceEngine:
    """Motor de generación de respuestas basado en el essence store."""

    def __init__(self, store: EssenceStore | None = None, provider=None):
        self.store = store or EssenceStore()
        self._provider = provider  # inyectado o lazy-loaded

    def _get_provider(self):
        if self._provider is None:
            from esence.essence.providers import get_provider
            self._provider = get_provider()
            logger.info(f"Provider AI: {self._provider.name}")
        return self._provider

    def _build_system_prompt(self, instruction: str = "") -> str:
        """Construye el system prompt completo desde el essence store."""
        identity = self.store.read_identity()
        context = self.store.read_context()
        patterns = self.store.read_patterns()

        maturity = calculate_maturity(self.store)
        label = maturity_label(maturity)

        patterns_text = "\n".join(
            f"- {p.get('description', str(p))}" for p in patterns
        ) or "(sin patrones aún — el agente está aprendiendo)"

        name = identity.get("name", config.node_name)
        did = identity.get("id", config.did())

        return SYSTEM_PROMPT_TEMPLATE.format(
            name=name,
            did=did,
            domain=config.domain,
            maturity_score=maturity,
            maturity_label=label,
            context=context or "(sin contexto acumulado aún)",
            patterns=patterns_text,
            instruction=instruction,
        )

    async def generate(
        self,
        user_message: str,
        context_messages: list[dict] | None = None,
        max_tokens: int = 1024,
    ) -> str:
        """Genera una respuesta propuesta. Retorna el texto."""
        if self.store.is_over_budget():
            return "[budget_exceeded: el nodo ha alcanzado su límite mensual de tokens]"

        provider = self._get_provider()
        system = self._build_system_prompt()
        messages = list(context_messages or [])
        messages.append({"role": "user", "content": user_message})

        response = await provider.complete(system, messages, max_tokens)
        self.store.record_usage(response.total_tokens)
        return response.text

    async def generate_stream(
        self,
        user_message: str,
        context_messages: list[dict] | None = None,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Versión streaming de generate()."""
        if self.store.is_over_budget():
            yield "[budget_exceeded]"
            return

        provider = self._get_provider()
        system = self._build_system_prompt()
        messages = list(context_messages or [])
        messages.append({"role": "user", "content": user_message})

        async for chunk in provider.stream(system, messages, max_tokens):
            yield chunk

    async def generate_self_response(self, owner_message: str) -> str:
        """El dueño habla con su propio agente (interfaz local)."""
        instruction = (
            "El dueño está hablando directamente con vos. "
            "Podés ser más reflexivo y personal. "
            "Podés hacer preguntas para conocerlo mejor."
        )
        system = self._build_system_prompt(instruction=instruction)
        provider = self._get_provider()

        response = await provider.complete(
            system,
            [{"role": "user", "content": owner_message}],
            max_tokens=1024,
        )
        self.store.record_usage(response.total_tokens)
        return response.text
