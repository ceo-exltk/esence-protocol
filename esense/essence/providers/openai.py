"""
esense/essence/providers/openai.py — Provider usando OpenAI API
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from esense.essence.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(BaseProvider):
    """Llama a la OpenAI API. Requiere OPENAI_API_KEY."""

    def __init__(self, model: str = _DEFAULT_MODEL):
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            from esense.config import config
            self._client = AsyncOpenAI(api_key=config.openai_api_key)
        return self._client

    async def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        client = self._get_client()
        all_messages = [{"role": "system", "content": system}, *messages]
        response = await client.chat.completions.create(
            model=self.model,
            messages=all_messages,
            max_tokens=max_tokens,
        )
        text = response.choices[0].message.content or ""
        return ProviderResponse(
            text=text,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
        )

    async def stream(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        all_messages = [{"role": "system", "content": system}, *messages]
        async with client.chat.completions.stream(
            model=self.model,
            messages=all_messages,
            max_tokens=max_tokens,
        ) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta

    @property
    def name(self) -> str:
        return f"openai/{self.model}"
