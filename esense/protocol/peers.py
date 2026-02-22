"""
esense/protocol/peers.py — Gestión de peers conocidos, trust scoring y gossip básico
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from esense.essence.store import EssenceStore

logger = logging.getLogger(__name__)

_DEFAULT_TRUST = 0.5
_MAX_TRUST = 1.0
_MIN_TRUST = 0.0


class PeerManager:
    """Gestiona la lista de peers con trust scoring y gossip."""

    def __init__(self, store: EssenceStore | None = None):
        self.store = store or EssenceStore()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # CRUD de peers
    # ------------------------------------------------------------------

    def get_all(self) -> list[dict[str, Any]]:
        return self.store.read_peers()

    def get_peer(self, did: str) -> dict[str, Any] | None:
        for peer in self.get_all():
            if peer.get("did") == did:
                return peer
        return None

    def add_or_update(self, did: str, **kwargs) -> dict[str, Any]:
        """Agrega o actualiza un peer. Retorna el peer actualizado."""
        existing = self.get_peer(did)
        if existing:
            peer = {**existing, **kwargs, "did": did, "updated_at": self._now()}
        else:
            peer = {
                "did": did,
                "trust_score": _DEFAULT_TRUST,
                "added_at": self._now(),
                "updated_at": self._now(),
                "message_count": 0,
                "last_seen": None,
                **kwargs,
            }
        self.store.upsert_peer(peer)
        return peer

    def remove(self, did: str) -> None:
        peers = [p for p in self.get_all() if p.get("did") != did]
        self.store.write_peers(peers)

    # ------------------------------------------------------------------
    # Trust scoring
    # ------------------------------------------------------------------

    def adjust_trust(self, did: str, delta: float) -> float:
        """Ajusta el trust score de un peer. Retorna el nuevo score."""
        peer = self.get_peer(did)
        if not peer:
            peer = self.add_or_update(did)
        current = peer.get("trust_score", _DEFAULT_TRUST)
        new_score = max(_MIN_TRUST, min(_MAX_TRUST, current + delta))
        self.add_or_update(did, trust_score=new_score)
        return new_score

    def record_interaction(self, did: str, successful: bool = True) -> None:
        """Registra una interacción con un peer y ajusta trust."""
        peer = self.get_peer(did) or self.add_or_update(did)
        count = peer.get("message_count", 0) + 1
        delta = 0.02 if successful else -0.05
        self.add_or_update(
            did,
            message_count=count,
            last_seen=self._now(),
            trust_score=max(_MIN_TRUST, min(_MAX_TRUST, peer.get("trust_score", _DEFAULT_TRUST) + delta)),
        )

    def trusted_peers(self, min_trust: float = 0.3) -> list[dict[str, Any]]:
        """Retorna peers con trust score >= min_trust."""
        return [p for p in self.get_all() if p.get("trust_score", 0) >= min_trust]

    # ------------------------------------------------------------------
    # Gossip — intercambio de listas de peers
    # ------------------------------------------------------------------

    def get_gossip_payload(self, max_peers: int = 20) -> list[str]:
        """Retorna lista de DIDs a compartir con otros nodos."""
        trusted = self.trusted_peers(min_trust=0.4)
        # Ordenar por trust desc, limitar
        sorted_peers = sorted(trusted, key=lambda p: p.get("trust_score", 0), reverse=True)
        return [p["did"] for p in sorted_peers[:max_peers]]

    def merge_gossip(self, incoming_dids: list[str], source_did: str) -> int:
        """
        Integra una lista de DIDs recibida por gossip.
        Retorna la cantidad de peers nuevos agregados.
        """
        added = 0
        for did in incoming_dids:
            if did == source_did:
                continue
            if not self.get_peer(did):
                self.add_or_update(
                    did,
                    trust_score=0.2,  # trust bajo para peers no conocidos
                    source=source_did,
                )
                added += 1
                logger.info(f"Nuevo peer via gossip de {source_did}: {did}")
        return added

    def peer_count(self) -> int:
        return len(self.get_all())

    def get_peer_display_name(self, did: str) -> str:
        """Retorna alias si existe, sino @node_name extraído del DID."""
        peer = self.get_peer(did)
        if peer and peer.get("alias"):
            return peer["alias"]
        parts = did.split(":")
        if len(parts) >= 4:
            return f"@{parts[3]}"
        return did
