"""
esence/protocol/transport.py — Envío/recepción HTTPS entre nodos Esence

Resuelve DID → URL, firma mensajes salientes, verifica firmas entrantes.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from esence.core.identity import Identity
from esence.protocol.message import EsenceMessage, parse_message

logger = logging.getLogger(__name__)

_DID_CACHE: dict[str, dict] = {}  # cache de DID documents resueltos


async def resolve_did(did: str, timeout: float = 10.0) -> dict[str, Any]:
    """
    Resuelve un DID:WBA a su DID Document.

    did:wba:domain:name → GET https://domain/.well-known/did.json
    Para localhost incluye el puerto si está en el DID.
    """
    if did in _DID_CACHE:
        return _DID_CACHE[did]

    # Parsear did:wba:domain:name
    parts = did.split(":")
    if len(parts) < 4 or parts[1] != "wba":
        raise ValueError(f"DID inválido: {did}")

    domain = parts[2]
    # Detectar puerto embebido en el dominio (ej: localhost%3A7777)
    if "%3A" in domain:
        domain = domain.replace("%3A", ":")

    url = f"https://{domain}/.well-known/did.json"
    # Para desarrollo local usar http
    if domain.startswith("localhost") or domain.startswith("127.0.0.1"):
        url = f"http://{domain}/.well-known/did.json"

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        did_doc = resp.json()

    _DID_CACHE[did] = did_doc
    return did_doc


def _extract_public_key_from_did_doc(did_doc: dict[str, Any]) -> str | None:
    """Extrae la public key base64url del primer verification method."""
    for vm in did_doc.get("verificationMethod", []):
        multibase = vm.get("publicKeyMultibase", "")
        if multibase.startswith("z"):
            # Quitar prefijo 'z' (multibase base58btc) — en nuestro caso es base64url con z
            return multibase[1:]
    return None


async def send_message(
    message: EsenceMessage,
    identity: Identity,
    timeout: float = 30.0,
) -> bool:
    """
    Envía un mensaje firmado al nodo destino.

    1. Resuelve el DID del destinatario
    2. Firma el mensaje
    3. POST a https://domain/anp/message
    """
    try:
        did_doc = await resolve_did(message.to_did, timeout=timeout)
    except Exception as e:
        logger.error(f"No se pudo resolver DID {message.to_did}: {e}")
        return False

    # Firmar
    message.signature = identity.sign(message.signable_bytes())

    # Construir URL de destino
    parts = message.to_did.split(":")
    domain = parts[2].replace("%3A", ":")
    scheme = "http" if domain.startswith("localhost") or domain.startswith("127.0.0.1") else "https"
    url = f"{scheme}://{domain}/anp/message"

    payload = message.model_dump()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            logger.info(f"Mensaje enviado a {message.to_did}: {resp.status_code}")
            return True
    except Exception as e:
        logger.error(f"Error enviando a {message.to_did}: {e}")
        return False


async def receive_message(
    payload: dict[str, Any],
) -> tuple[EsenceMessage, bool]:
    """
    Procesa un mensaje entrante:
    1. Parsea el payload al tipo correcto
    2. Resuelve el DID del remitente
    3. Verifica la firma

    Retorna (mensaje, firma_válida).
    """
    message = parse_message(payload)
    signature = message.signature

    if not signature:
        logger.warning(f"Mensaje sin firma de {message.from_did}")
        return message, False

    try:
        did_doc = await resolve_did(message.from_did)
        pub_key_b64 = _extract_public_key_from_did_doc(did_doc)
        if not pub_key_b64:
            logger.warning(f"No se encontró public key en DID doc de {message.from_did}")
            return message, False

        # Crear copia sin firma para verificar
        msg_copy = message.model_copy(update={"signature": None})
        valid = Identity.verify_with_public_key(
            pub_key_b64,
            msg_copy.signable_bytes(),
            signature,
        )
        if not valid:
            logger.warning(f"Firma inválida en mensaje de {message.from_did}")
        return message, valid

    except Exception as e:
        logger.error(f"Error verificando firma de {message.from_did}: {e}")
        return message, False
