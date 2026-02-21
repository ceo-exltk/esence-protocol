"""
tests/test_identity.py — Tests de identidad Ed25519 y DID:WBA
"""
from __future__ import annotations

from pathlib import Path

import pytest

from esence.core.identity import Identity


def test_generate_creates_valid_did():
    identity = Identity.generate("alice", "example.com")
    assert identity.did == "did:wba:example.com:alice"


def test_sign_and_verify():
    identity = Identity.generate("alice", "example.com")
    data = b"esence:test:payload"
    sig = identity.sign(data)
    assert isinstance(sig, str)
    assert identity.verify(data, sig)


def test_verify_fails_with_wrong_data():
    identity = Identity.generate("alice", "example.com")
    data = b"original"
    sig = identity.sign(data)
    assert not identity.verify(b"tampered", sig)


def test_verify_fails_with_wrong_sig():
    identity = Identity.generate("alice", "example.com")
    data = b"data"
    # Completely fabricated invalid signature (88 chars of zeros is a valid b64url length for Ed25519)
    bad_sig = "A" * 86 + "AA"  # 88 chars but wrong bytes
    assert not identity.verify(data, bad_sig)


def test_public_key_b64_is_string():
    identity = Identity.generate("alice", "example.com")
    pub = identity.public_key_b64()
    assert isinstance(pub, str)
    assert len(pub) > 0


def test_to_did_document_structure():
    identity = Identity.generate("alice", "example.com")
    doc = identity.to_did_document()
    assert doc["id"] == "did:wba:example.com:alice"
    assert "@context" in doc
    assert "verificationMethod" in doc
    assert len(doc["verificationMethod"]) == 1
    vm = doc["verificationMethod"][0]
    assert vm["type"] == "Ed25519VerificationKey2020"
    assert vm["publicKeyMultibase"].startswith("z")


def test_save_and_load(tmp_path: Path):
    identity = Identity.generate("bob", "example.com")

    # Necesitamos un identity.json o did.json para cargar
    import json
    (tmp_path / "keys").mkdir()
    identity_data = {"id": identity.did, "name": "bob"}
    (tmp_path / "identity.json").write_text(json.dumps(identity_data))

    identity.save(tmp_path)

    loaded = Identity.load(tmp_path)
    assert loaded.did == identity.did

    # Verificar que las claves son equivalentes
    data = b"verification"
    sig = identity.sign(data)
    assert loaded.verify(data, sig)


def test_verify_with_public_key_cross():
    """Verifica firma de una identity con la public key de otra instance."""
    identity = Identity.generate("charlie", "example.com")
    data = b"cross-verify"
    sig = identity.sign(data)
    pub_b64 = identity.public_key_b64()
    assert Identity.verify_with_public_key(pub_b64, data, sig)


def test_verify_with_wrong_public_key():
    """Firma de una key no verifica con otra key."""
    id1 = Identity.generate("alice", "example.com")
    id2 = Identity.generate("bob", "example.com")
    data = b"data"
    sig = id1.sign(data)
    # La public key de id2 no debe verificar firma de id1
    assert not Identity.verify_with_public_key(id2.public_key_b64(), data, sig)
