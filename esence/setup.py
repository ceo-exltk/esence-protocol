"""
esence/setup.py — Setup interactivo del nodo Esence

Genera keys, crea essence-store/, escribe archivos iniciales.
Runnable como: python3 -m esence.setup
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _prompt(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"  {question}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return answer if answer else default


def _print_header() -> None:
    print()
    print("  ███████╗███████╗███████╗███╗   ██╗ ██████╗███████╗")
    print("  ██╔════╝██╔════╝██╔════╝████╗  ██║██╔════╝██╔════╝")
    print("  █████╗  ███████╗█████╗  ██╔██╗ ██║██║     █████╗  ")
    print("  ██╔══╝  ╚════██║██╔══╝  ██║╚██╗██║██║     ██╔══╝  ")
    print("  ███████╗███████║███████╗██║ ╚████║╚██████╗███████╗")
    print("  ╚══════╝╚══════╝╚══════╝╚═╝  ╚═══╝ ╚═════╝╚══════╝")
    print()
    print("  Protocol v0.2 — Genesis Node Setup")
    print()


def run_setup() -> None:
    _print_header()

    root = Path(__file__).parent.parent

    # ------------------------------------------------------------------
    # .env
    # ------------------------------------------------------------------
    env_path = root / ".env"
    env_example = root / ".env.example"

    if not env_path.exists() and env_example.exists():
        import shutil
        shutil.copy(env_example, env_path)

    # Leer .env existente si hay
    existing_env: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                existing_env[k.strip()] = v.strip()

    print("  Configuración del nodo")
    print("  " + "─" * 40)

    node_name = _prompt(
        "Nombre del nodo (sin espacios)",
        existing_env.get("ESENCE_NODE_NAME", "node0"),
    )
    domain = _prompt(
        "Dominio (localhost para desarrollo)",
        existing_env.get("ESENCE_DOMAIN", "localhost"),
    )
    port = _prompt(
        "Puerto de la interfaz",
        existing_env.get("ESENCE_PORT", "7777"),
    )
    api_key = _prompt(
        "Anthropic API key",
        existing_env.get("ANTHROPIC_API_KEY", ""),
    )
    donation_pct = _prompt(
        "% de capacidad a compartir con la red",
        existing_env.get("ESENCE_DONATION_PCT", "10"),
    )
    public_url = _prompt(
        "URL pública (ngrok, VPS) — Enter para saltar",
        existing_env.get("ESENCE_PUBLIC_URL", ""),
    )

    # Escribir .env
    env_content = f"""# Esence Node Configuration
# Generado por esence/setup.py — {datetime.now(timezone.utc).isoformat()}

ESENCE_PROVIDER=anthropic
ANTHROPIC_API_KEY={api_key}

ESENCE_NODE_NAME={node_name}
ESENCE_DOMAIN={domain}
ESENCE_PORT={port}
ESENCE_DONATION_PCT={donation_pct}
ESENCE_PUBLIC_URL={public_url}
"""
    env_path.write_text(env_content)
    print(f"\n  ✓ .env escrito")

    # ------------------------------------------------------------------
    # Importar con la config actualizada
    # ------------------------------------------------------------------
    # Recargar env para que config use los nuevos valores
    from dotenv import load_dotenv
    load_dotenv(env_path, override=True)

    import os
    os.environ["ESENCE_NODE_NAME"] = node_name
    os.environ["ESENCE_DOMAIN"] = domain
    os.environ["ESENCE_PORT"] = port

    # ------------------------------------------------------------------
    # Generar identidad
    # ------------------------------------------------------------------
    from esence.core.identity import Identity

    store_dir = root / "essence-store"

    if (store_dir / "keys" / "private.pem").exists():
        print(f"  ✓ Identidad existente encontrada — se mantiene")
        identity = Identity.load(store_dir)
    else:
        print(f"  Generando par de claves Ed25519...")
        identity = Identity.generate(node_name, domain)
        identity.save(store_dir)
        print(f"  ✓ Keys generadas y guardadas en essence-store/keys/")

    print(f"  ✓ DID: {identity.did}")

    # ------------------------------------------------------------------
    # Inicializar essence-store
    # ------------------------------------------------------------------
    from esence.essence.store import EssenceStore

    identity_data = {
        "id": identity.did,
        "name": node_name,
        "domain": domain,
        "port": int(port),
        "languages": ["es"],
        "values": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    store = EssenceStore(store_dir)
    store.initialize(identity_data)
    print(f"  ✓ essence-store/ inicializado")

    # Verificar firma como test
    test_payload = b"esence:genesis"
    sig = identity.sign(test_payload)
    assert identity.verify(test_payload, sig), "Error: verificación de firma falló"
    print(f"  ✓ Test de firma Ed25519: OK")

    # ------------------------------------------------------------------
    # Resumen
    # ------------------------------------------------------------------
    print()
    print("  " + "─" * 40)
    print(f"  Nodo listo:")
    print(f"    DID    : {identity.did}")
    print(f"    Puerto : {port}")
    print(f"    Store  : essence-store/")
    print()
    print("  Ejecutá ./start.sh para arrancar el nodo.")
    print()


if __name__ == "__main__":
    run_setup()
