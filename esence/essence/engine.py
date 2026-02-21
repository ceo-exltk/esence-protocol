"""
esence/essence/engine.py — Interfaz async con el AI provider

Construye el system prompt desde el essence store y genera respuestas.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import anthropic

from esence.config import config
from esence.essence.maturity import calculate_maturity, maturity_label
from esence.essence.store import EssenceStore


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

    def __init__(self, store: EssenceStore | None = None):
        self.store = store or EssenceStore()
        self._client: anthropic.AsyncAnthropic | None = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
        return self._client

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
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 1024,
    ) -> str:
        """
        Genera una respuesta propuesta para el mensaje entrante.
        Retorna el texto de la respuesta.
        """
        if self.store.is_over_budget():
            return "[budget_exceeded: el nodo ha alcanzado su límite mensual de tokens]"

        client = self._get_client()
        system = self._build_system_prompt()

        messages = list(context_messages or [])
        messages.append({"role": "user", "content": user_message})

        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )

        # Registrar uso
        usage = response.usage
        tokens_used = (usage.input_tokens or 0) + (usage.output_tokens or 0)
        self.store.record_usage(tokens_used)

        return response.content[0].text if response.content else ""

    async def generate_stream(
        self,
        user_message: str,
        context_messages: list[dict] | None = None,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Versión streaming de generate()."""
        if self.store.is_over_budget():
            yield "[budget_exceeded]"
            return

        client = self._get_client()
        system = self._build_system_prompt()

        messages = list(context_messages or [])
        messages.append({"role": "user", "content": user_message})

        async with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

            # Registrar uso al final
            final = await stream.get_final_message()
            usage = final.usage
            tokens_used = (usage.input_tokens or 0) + (usage.output_tokens or 0)
            self.store.record_usage(tokens_used)

    async def generate_self_response(self, owner_message: str) -> str:
        """El dueño habla con su propio agente (interfaz local)."""
        instruction = (
            "El dueño está hablando directamente con vos. "
            "Podés ser más reflexivo y personal. "
            "Podés hacer preguntas para conocerlo mejor."
        )
        system = self._build_system_prompt(instruction=instruction)

        client = self._get_client()
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": owner_message}],
        )
        usage = response.usage
        self.store.record_usage((usage.input_tokens or 0) + (usage.output_tokens or 0))
        return response.content[0].text if response.content else ""
