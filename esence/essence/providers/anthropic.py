"""
esence/essence/providers/anthropic.py — Provider usando Anthropic API
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from esence.essence.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"


class AnthropicProvider(BaseProvider):
    """Llama a la Anthropic API con la SDK oficial. Requiere ANTHROPIC_API_KEY."""

    def __init__(self, model: str = _DEFAULT_MODEL):
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            from esence.config import config
            self._client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
        return self._client

    async def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        client = self._get_client()
        response = await client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        text = response.content[0].text if response.content else ""
        return ProviderResponse(
            text=text,
            input_tokens=response.usage.input_tokens or 0,
            output_tokens=response.usage.output_tokens or 0,
        )

    async def stream(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        async with client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    @property
    def name(self) -> str:
        return f"anthropic/{self.model}"
