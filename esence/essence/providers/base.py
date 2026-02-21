"""
esence/essence/providers/base.py — Interface base para AI providers
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class ProviderResponse:
    """Respuesta normalizada de cualquier provider."""
    text: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class BaseProvider(ABC):
    """Interface que todo AI provider debe implementar."""

    @abstractmethod
    async def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        """
        Genera una respuesta completa.

        Args:
            system: System prompt
            messages: Lista de {role: user|assistant, content: str}
            max_tokens: Límite de tokens en la respuesta

        Returns:
            ProviderResponse con texto y conteo de tokens
        """
        ...

    async def stream(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """
        Versión streaming. Por defecto delega a complete() y emite de a un chunk.
        Los providers que soporten streaming nativo pueden override este método.
        """
        response = await self.complete(system, messages, max_tokens)
        yield response.text

    @property
    def name(self) -> str:
        return self.__class__.__name__
