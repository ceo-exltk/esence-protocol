"""
esence/core/identity.py — DID:WBA, Ed25519 key pair, firma y verificación
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from esence.config import config


def _b64url(data: bytes) -> str:
    """Encode bytes to base64url (no padding)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    """Decode base64url string (pad as needed)."""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


class Identity:
    """Identidad Ed25519 de un nodo Esence."""

    def __init__(self, private_key: Ed25519PrivateKey, did: str):
        self._private_key = private_key
        self._public_key: Ed25519PublicKey = private_key.public_key()
        self.did = did

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def generate(cls, node_name: str, domain: str) -> "Identity":
        """Genera un nuevo key pair Ed25519."""
        private_key = Ed25519PrivateKey.generate()
        did = f"did:wba:{domain}:{node_name}"
        return cls(private_key, did)

    @classmethod
    def load(cls, store_dir: Path | None = None) -> "Identity":
        """Carga la identidad desde essence-store/keys/."""
        store_dir = store_dir or config.essence_store_dir
        keys_dir = store_dir / "keys"
        private_pem = (keys_dir / "private.pem").read_bytes()
        private_key = Ed25519PrivateKey.from_private_bytes(
            _extract_raw_ed25519(private_pem)
        )
        # Leer DID desde did.json (DID Document) o identity.json (essence store)
        did_doc_path = store_dir / "did.json"
        identity_path = store_dir / "identity.json"
        if did_doc_path.exists():
            did = json.loads(did_doc_path.read_text())["id"]
        elif identity_path.exists():
            did = json.loads(identity_path.read_text())["id"]
        else:
            raise FileNotFoundError(f"No se encontró did.json ni identity.json en {store_dir}")
        return cls(private_key, did)

    @classmethod
    def load_or_generate(cls, store_dir: Path | None = None) -> "Identity":
        """Carga la identidad si existe, sino la genera."""
        store_dir = store_dir or config.essence_store_dir
        keys_dir = store_dir / "keys"
        if (keys_dir / "private.pem").exists():
            return cls.load(store_dir)
        identity = cls.generate(config.node_name, config.domain)
        identity.save(store_dir)
        return identity

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, store_dir: Path | None = None) -> None:
        """Guarda keys y did.json en essence-store/."""
        store_dir = store_dir or config.essence_store_dir
        keys_dir = store_dir / "keys"
        keys_dir.mkdir(parents=True, exist_ok=True)

        # Guardar private key en PEM
        private_pem = self._private_key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        )
        (keys_dir / "private.pem").write_bytes(private_pem)
        (keys_dir / "private.pem").chmod(0o600)

        # Guardar public key en PEM
        public_pem = self._public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        (keys_dir / "public.pem").write_bytes(public_pem)

        # Guardar did.json
        did_doc = self.to_did_document()
        (store_dir / "did.json").write_text(json.dumps(did_doc, indent=2))

    # ------------------------------------------------------------------
    # Firma y verificación
    # ------------------------------------------------------------------

    def sign(self, data: bytes) -> str:
        """Firma bytes, retorna base64url."""
        signature = self._private_key.sign(data)
        return _b64url(signature)

    def verify(self, data: bytes, signature_b64: str) -> bool:
        """Verifica una firma base64url contra la propia public key."""
        try:
            sig_bytes = _b64url_decode(signature_b64)
            self._public_key.verify(sig_bytes, data)
            return True
        except Exception:
            return False

    @staticmethod
    def verify_with_public_key(public_key_b64: str, data: bytes, signature_b64: str) -> bool:
        """Verifica una firma con una public key externa (base64url)."""
        try:
            pub_bytes = _b64url_decode(public_key_b64)
            pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
            sig_bytes = _b64url_decode(signature_b64)
            pub_key.verify(sig_bytes, data)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # DID Document
    # ------------------------------------------------------------------

    def public_key_b64(self) -> str:
        """Raw public key bytes en base64url."""
        raw = self._public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        return _b64url(raw)

    def to_did_document(self) -> dict[str, Any]:
        """Genera el DID Document W3C compatible."""
        pub_b64 = self.public_key_b64()
        vm_id = f"{self.did}#key-1"
        return {
            "@context": [
                "https://www.w3.org/ns/did/v1",
                "https://w3id.org/security/suites/ed25519-2020/v1",
            ],
            "id": self.did,
            "verificationMethod": [
                {
                    "id": vm_id,
                    "type": "Ed25519VerificationKey2020",
                    "controller": self.did,
                    "publicKeyMultibase": f"z{pub_b64}",
                }
            ],
            "authentication": [vm_id],
            "assertionMethod": [vm_id],
            "created": datetime.now(timezone.utc).isoformat(),
        }


# ------------------------------------------------------------------
# Helpers internos
# ------------------------------------------------------------------

def _extract_raw_ed25519(pem_bytes: bytes) -> bytes:
    """Extrae los 32 bytes raw de una private key Ed25519 en PEM/PKCS8."""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    key = load_pem_private_key(pem_bytes, password=None)
    return key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
