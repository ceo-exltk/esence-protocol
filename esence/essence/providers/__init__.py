"""
esence/essence/providers — Abstracción de AI providers

Providers disponibles:
- anthropic   : Anthropic API (requiere ANTHROPIC_API_KEY)
- claude_code : Claude Code CLI subprocess (sin API key separada)
- ollama      : Ollama local (sin API key, requiere ollama corriendo)
- openai      : OpenAI API (requiere OPENAI_API_KEY)
"""
from __future__ import annotations

from esence.essence.providers.base import BaseProvider, ProviderResponse


def get_provider(name: str | None = None) -> BaseProvider:
    """
    Retorna una instancia del provider configurado.

    Orden de preferencia si no se especifica:
    1. Lo que diga ESENCE_PROVIDER en .env
    2. claude_code si el CLI está disponible
    3. anthropic si hay ANTHROPIC_API_KEY
    4. ollama como último recurso
    """
    from esence.config import config

    provider_name = (name or config.provider).lower()

    if provider_name == "anthropic":
        from esence.essence.providers.anthropic import AnthropicProvider
        return AnthropicProvider()

    if provider_name == "claude_code":
        from esence.essence.providers.claude_code import ClaudeCodeProvider
        return ClaudeCodeProvider()

    if provider_name == "ollama":
        from esence.essence.providers.ollama import OllamaProvider
        return OllamaProvider()

    if provider_name == "openai":
        from esence.essence.providers.openai import OpenAIProvider
        return OpenAIProvider()

    # Auto-detect
    if _claude_cli_available():
        from esence.essence.providers.claude_code import ClaudeCodeProvider
        return ClaudeCodeProvider()

    if config.anthropic_api_key:
        from esence.essence.providers.anthropic import AnthropicProvider
        return AnthropicProvider()

    from esence.essence.providers.ollama import OllamaProvider
    return OllamaProvider()


def _claude_cli_available() -> bool:
    import shutil
    return shutil.which("claude") is not None


__all__ = ["BaseProvider", "ProviderResponse", "get_provider"]
