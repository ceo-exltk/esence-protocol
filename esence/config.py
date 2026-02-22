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

    # AI provider (anthropic | claude_code | ollama | openai)
    provider: str = os.getenv("ESENCE_PROVIDER", "auto")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    # Identidad del nodo
    node_name: str = os.getenv("ESENCE_NODE_NAME", "node0")
    domain: str = os.getenv("ESENCE_DOMAIN", "localhost")

    # Red
    donation_pct: int = int(os.getenv("ESENCE_DONATION_PCT", "10"))
    port: int = int(os.getenv("ESENCE_PORT", "7777"))
    bootstrap_peer: str = os.getenv("ESENCE_BOOTSTRAP_PEER", "")
    public_url: str = os.getenv("ESENCE_PUBLIC_URL", "")  # ej: "https://abc123.ngrok.io"

    # Dev
    dev_skip_sig: bool = os.getenv("ESENCE_SKIP_SIG_VERIFY", "").lower() in ("1", "true", "yes")

    # Paths
    root_dir: Path = _ROOT
    essence_store_dir: Path = _ROOT / "essence-store"

    @classmethod
    def effective_domain(cls) -> str:
        """Dominio público si PUBLIC_URL está seteado, sino domain local."""
        if cls.public_url:
            from urllib.parse import urlparse
            return urlparse(cls.public_url).netloc  # "abc.ngrok.io"
        return cls.domain

    @classmethod
    def effective_did_domain(cls) -> str:
        """Dominio para usar en DIDs.
        Para localhost incluye el puerto URL-encoded (ej: localhost%3A7777)
        para que resolve_did pueda construir la URL correcta."""
        if cls.public_url:
            from urllib.parse import urlparse
            return urlparse(cls.public_url).netloc
        is_local = cls.domain.startswith("localhost") or cls.domain.startswith("127.")
        if is_local:
            return f"{cls.domain}%3A{cls.port}"
        return cls.domain

    @classmethod
    def did(cls) -> str:
        return f"did:wba:{cls.effective_did_domain()}:{cls.node_name}"

    @classmethod
    def did_document_url(cls) -> str:
        domain = cls.effective_domain()
        if cls.public_url:
            return f"{cls.public_url.rstrip('/')}/.well-known/did.json"
        # localhost: http + puerto explícito
        is_local = domain.startswith("localhost") or domain.startswith("127.")
        port_suffix = f":{cls.port}" if is_local else ""
        scheme = "http" if is_local else "https"
        return f"{scheme}://{domain}{port_suffix}/.well-known/did.json"

    @classmethod
    def validate(cls) -> list[str]:
        """Retorna lista de errores de configuración."""
        errors = []
        if not cls.node_name or cls.node_name == "yourname":
            errors.append("ESENCE_NODE_NAME no configurado")
        if cls.provider == "anthropic" and not cls.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY no configurado")
        if cls.provider == "openai" and not cls.openai_api_key:
            errors.append("OPENAI_API_KEY no configurado")
        return errors


# Singleton accesible directamente
config = Config()
