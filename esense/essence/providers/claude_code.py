"""
esense/essence/providers/claude_code.py — Provider usando Claude Code CLI

Invoca `claude -p <prompt>` como subprocess. No requiere API key separada —
usa la sesión activa de Claude Code en el sistema.
"""
from __future__ import annotations

import asyncio
import logging
import shutil

from esense.essence.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)

_CLI_PATH = shutil.which("claude") or "claude"


class ClaudeCodeProvider(BaseProvider):
    """
    Ejecuta el CLI de Claude Code como subprocess async.

    Ventajas:
    - Sin API key separada (usa la sesión de Claude Code)
    - Funciona out-of-the-box en cualquier máquina con Claude Code instalado

    Limitaciones:
    - No reporta conteo de tokens (se estima por longitud de texto)
    - No soporta streaming real (devuelve respuesta completa)
    """

    def __init__(self, timeout: float = 120.0):
        self.timeout = timeout

    async def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        # Construir el prompt combinando system + historial + último mensaje
        full_prompt = _build_prompt(system, messages)

        # Limpiar CLAUDECODE del entorno para evitar el error de sesión anidada
        import os
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        try:
            proc = await asyncio.create_subprocess_exec(
                _CLI_PATH,
                "--print",
                full_prompt,
                "--output-format", "text",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Claude Code CLI timeout ({self.timeout}s)")
            return ProviderResponse(text="[timeout: el CLI de Claude Code no respondió]")
        except FileNotFoundError:
            logger.error(f"Claude Code CLI no encontrado en: {_CLI_PATH}")
            return ProviderResponse(text="[error: claude CLI no encontrado]")

        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error(f"Claude Code CLI error (rc={proc.returncode}): {err}")
            return ProviderResponse(text=f"[error: {err[:200]}]")

        text = stdout.decode().strip()

        # Estimar tokens (aprox 4 chars por token)
        input_tokens = len(full_prompt) // 4
        output_tokens = len(text) // 4

        return ProviderResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    @property
    def name(self) -> str:
        return "claude_code/cli"


def _build_prompt(system: str, messages: list[dict]) -> str:
    """
    Combina system prompt e historial en un único string para el CLI.

    El CLI de Claude Code acepta un único prompt en --print, así que
    concatenamos todo con separadores claros.
    """
    parts = [f"<system>\n{system}\n</system>"]

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            parts.append(f"<human>\n{content}\n</human>")
        else:
            parts.append(f"<assistant>\n{content}\n</assistant>")

    return "\n\n".join(parts)
