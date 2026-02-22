"""
esense/essence/providers/ollama.py — Provider usando Ollama local

Requiere Ollama corriendo en localhost:11434.
Sin API key. Ideal para uso completamente offline.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from esense.essence.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)

_DEFAULT_HOST = "http://localhost:11434"
_DEFAULT_MODEL = "llama3.2"


class OllamaProvider(BaseProvider):
    """Llama a la API REST de Ollama. Sin API key."""

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        host: str = _DEFAULT_HOST,
        timeout: float = 120.0,
    ):
        self.model = model
        self.host = host
        self.timeout = timeout

    async def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.host}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.ConnectError:
            logger.error(f"No se pudo conectar a Ollama en {self.host}")
            return ProviderResponse(text="[error: Ollama no está corriendo]")
        except Exception as e:
            logger.error(f"Error llamando a Ollama: {e}")
            return ProviderResponse(text=f"[error: {e}]")

        text = data.get("message", {}).get("content", "")
        eval_count = data.get("eval_count", 0)
        prompt_eval_count = data.get("prompt_eval_count", 0)

        return ProviderResponse(
            text=text,
            input_tokens=prompt_eval_count,
            output_tokens=eval_count,
        )

    async def stream(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": True,
            "options": {"num_predict": max_tokens},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", f"{self.host}/api/chat", json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line:
                            chunk = json.loads(line)
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                yield token
                            if chunk.get("done"):
                                break
        except Exception as e:
            logger.error(f"Error streaming desde Ollama: {e}")
            yield f"[error: {e}]"

    @property
    def name(self) -> str:
        return f"ollama/{self.model}"
