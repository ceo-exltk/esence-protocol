"""
esense/essence/engine.py — Motor de generación de respuestas

Construye el system prompt desde el essence store y delega la generación
al provider configurado (anthropic, claude_code, ollama, openai).
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from esense.config import config
from esense.essence.maturity import calculate_maturity, maturity_label
from esense.essence.store import EssenceStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """Sos el agente digital de {name} en la red Esense.

## Quién sos
{context}

## Cómo respondés
{patterns}

## Ejemplos reales de tu estilo (últimas respuestas corregidas por {name})
{corrections_examples}

## Reglas
- Respondés en primera persona como {name}, no como IA.
- Sos directo. No ponés saludos formales, no usás frases de cierre corporativas.
- Calibrá la longitud: si te llega algo corto, respondé corto. Si es complejo, desarrollá.
- Antes de comprometerte a algo importante, decís que lo consultás con {name}.
- Si no sabés algo concreto sobre {name}, decís que no sabés en lugar de inventar.
- Nunca expliques que sos un agente de IA a menos que te lo pregunten directamente.

{instruction}"""


class EssenceEngine:
    """Motor de generación de respuestas basado en el essence store."""

    def __init__(self, store: EssenceStore | None = None, provider=None):
        self.store = store or EssenceStore()
        self._provider = provider  # inyectado o lazy-loaded

    def _get_provider(self):
        if self._provider is None:
            from esense.essence.providers import get_provider
            self._provider = get_provider()
            logger.info(f"Provider AI: {self._provider.name}")
        return self._provider

    def _build_system_prompt(
        self,
        instruction: str = "",
        sender_name: str | None = None,
    ) -> str:
        """Construye el system prompt completo desde el essence store."""
        identity = self.store.read_identity()
        context = self.store.read_context()
        patterns = self.store.read_patterns()
        corrections = self.store.read_corrections()

        name = identity.get("name", config.node_name)

        # Patrones de razonamiento
        patterns_text = "\n".join(
            f"- {p.get('description', str(p))}" for p in patterns
        ) or "(sin patrones aún — respondé según tu esencia y corregí cuando corresponda)"

        # Últimas 4 correcciones como ejemplos de estilo (solo las editadas)
        examples = []
        for c in corrections[-8:]:
            edited = c.get("edited", "").strip()
            original = c.get("original", "").strip()
            if edited and edited != original:
                examples.append(f'→ "{edited}"')
        if examples:
            corrections_examples = (
                "Así respondiste vos (no el agente automático) en conversaciones recientes:\n"
                + "\n".join(examples[-4:])
            )
        else:
            corrections_examples = "(sin correcciones aún — el agente aprende con el uso)"

        # Receptor conocido
        instr_parts = []
        if sender_name:
            instr_parts.append(f"Estás respondiendo a **{sender_name}**.")
        if instruction:
            instr_parts.append(instruction)
        instruction_block = "\n".join(instr_parts)

        return SYSTEM_PROMPT_TEMPLATE.format(
            name=name,
            context=context or f"Soy {name}, usuario de la red Esense.",
            patterns=patterns_text,
            corrections_examples=corrections_examples,
            instruction=instruction_block,
        )

    @staticmethod
    def _calibrate_tokens(user_message: str, requested: int) -> int:
        """Ajusta el límite de tokens según la longitud del mensaje entrante."""
        words = len(user_message.split())
        if words <= 10:
            return min(requested, 256)   # respuesta corta para mensaje corto
        if words <= 40:
            return min(requested, 512)
        return requested                  # mensaje largo → tokens completos

    async def generate(
        self,
        user_message: str,
        context_messages: list[dict] | None = None,
        max_tokens: int = 1024,
        sender_name: str | None = None,
    ) -> str:
        """Genera una respuesta propuesta. Retorna el texto."""
        if self.store.is_over_budget():
            return "[budget_exceeded: el nodo ha alcanzado su límite mensual de tokens]"

        provider = self._get_provider()
        system = self._build_system_prompt(sender_name=sender_name)
        messages = list(context_messages or [])
        messages.append({"role": "user", "content": user_message})

        tokens = self._calibrate_tokens(user_message, max_tokens)
        response = await provider.complete(system, messages, tokens)
        self.store.record_usage(response.total_tokens)
        return response.text

    async def generate_stream(
        self,
        user_message: str,
        context_messages: list[dict] | None = None,
        max_tokens: int = 1024,
        sender_name: str | None = None,
    ) -> AsyncIterator[str]:
        """Versión streaming de generate()."""
        if self.store.is_over_budget():
            yield "[budget_exceeded]"
            return

        provider = self._get_provider()
        system = self._build_system_prompt(sender_name=sender_name)
        messages = list(context_messages or [])
        messages.append({"role": "user", "content": user_message})

        tokens = self._calibrate_tokens(user_message, max_tokens)
        async for chunk in provider.stream(system, messages, tokens):
            yield chunk

    async def generate_self_response(
        self, owner_message: str, context_messages: list[dict] | None = None
    ) -> AsyncIterator[str]:
        """El dueño habla con su propio agente. Streaming."""
        if self.store.is_over_budget():
            yield "[budget_exceeded]"
            return

        instruction = (
            "El dueño está hablando directamente con vos en modo privado. "
            "Podés ser más reflexivo, hacerle preguntas, pensar en voz alta. "
            "No actúes como asistente genérico — respondé como la extensión de él."
        )
        system = self._build_system_prompt(instruction=instruction)
        provider = self._get_provider()
        messages = list(context_messages or [])
        messages.append({"role": "user", "content": owner_message})
        tokens = self._calibrate_tokens(owner_message, 1024)

        total_tokens = 0
        async for chunk in provider.stream(system, messages, tokens):
            yield chunk
