"""
esence/config.py — Configuración del nodo cargada desde .env
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Cargar .env desde la raíz del proyecto
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")


class Config:
    """Settings del nodo Esence. Todos los valores vienen de variables de entorno."""

    # AI provider
    provider: str = os.getenv("ESENCE_PROVIDER", "anthropic")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    # Identidad del nodo
    node_name: str = os.getenv("ESENCE_NODE_NAME", "node0")
    domain: str = os.getenv("ESENCE_DOMAIN", "localhost")

    # Red
    donation_pct: int = int(os.getenv("ESENCE_DONATION_PCT", "10"))
    port: int = int(os.getenv("ESENCE_PORT", "7777"))

    # Paths
    root_dir: Path = _ROOT
    essence_store_dir: Path = _ROOT / "essence-store"

    @classmethod
    def did(cls) -> str:
        return f"did:wba:{cls.domain}:{cls.node_name}"

    @classmethod
    def did_document_url(cls) -> str:
        port_suffix = f":{cls.port}" if cls.domain == "localhost" else ""
        return f"https://{cls.domain}{port_suffix}/.well-known/did.json"

    @classmethod
    def validate(cls) -> list[str]:
        """Retorna lista de errores de configuración."""
        errors = []
        if not cls.node_name or cls.node_name == "yourname":
            errors.append("ESENCE_NODE_NAME no configurado")
        if cls.provider == "anthropic" and not cls.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY no configurado")
        return errors


# Singleton accesible directamente
config = Config()
