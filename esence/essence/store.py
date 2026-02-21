"""
esence/essence/store.py — Leer/escribir el essence store (archivos locales)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from esence.config import config


class EssenceStore:
    """Interfaz de acceso al essence-store/ local."""

    def __init__(self, store_dir: Path | None = None):
        self.dir = store_dir or config.essence_store_dir

    # ------------------------------------------------------------------
    # Inicialización
    # ------------------------------------------------------------------

    def initialize(self, identity_data: dict[str, Any]) -> None:
        """Crea la estructura de directorios y archivos iniciales."""
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "threads").mkdir(exist_ok=True)
        (self.dir / "keys").mkdir(exist_ok=True)

        if not (self.dir / "identity.json").exists():
            self.write_identity(identity_data)

        if not (self.dir / "patterns.json").exists():
            self.write_patterns([])

        if not (self.dir / "context.md").exists():
            (self.dir / "context.md").write_text(
                "# Contexto del nodo\n\n"
                "Este archivo acumula conocimiento sobre el dueño del nodo.\n"
                "Será editado automáticamente por el sistema y manualmente por el dueño.\n"
            )

        if not (self.dir / "corrections.log").exists():
            (self.dir / "corrections.log").write_text("")

        if not (self.dir / "peers.json").exists():
            self.write_peers([])

        if not (self.dir / "budget.json").exists():
            self.write_budget({
                "monthly_limit_tokens": 500_000,
                "used_tokens": 0,
                "donation_pct": config.donation_pct,
                "calls_total": 0,
                "last_reset": datetime.now(timezone.utc).isoformat(),
            })

    # ------------------------------------------------------------------
    # identity.json
    # ------------------------------------------------------------------

    def read_identity(self) -> dict[str, Any]:
        path = self.dir / "identity.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text())

    def write_identity(self, data: dict[str, Any]) -> None:
        (self.dir / "identity.json").write_text(json.dumps(data, indent=2))

    # ------------------------------------------------------------------
    # patterns.json
    # ------------------------------------------------------------------

    def read_patterns(self) -> list[dict[str, Any]]:
        path = self.dir / "patterns.json"
        if not path.exists():
            return []
        return json.loads(path.read_text())

    def write_patterns(self, patterns: list[dict[str, Any]]) -> None:
        (self.dir / "patterns.json").write_text(json.dumps(patterns, indent=2))

    def add_pattern(self, pattern: dict[str, Any]) -> None:
        patterns = self.read_patterns()
        patterns.append(pattern)
        self.write_patterns(patterns)

    # ------------------------------------------------------------------
    # context.md
    # ------------------------------------------------------------------

    def read_context(self) -> str:
        path = self.dir / "context.md"
        if not path.exists():
            return ""
        return path.read_text()

    def write_context(self, content: str) -> None:
        (self.dir / "context.md").write_text(content)

    def append_context(self, section: str, content: str) -> None:
        existing = self.read_context()
        self.write_context(f"{existing}\n## {section}\n\n{content}\n")

    # ------------------------------------------------------------------
    # corrections.log (JSONL)
    # ------------------------------------------------------------------

    def append_correction(self, correction: dict[str, Any]) -> None:
        """Agrega una corrección al log JSONL."""
        correction.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        with open(self.dir / "corrections.log", "a") as f:
            f.write(json.dumps(correction) + "\n")

    def read_corrections(self) -> list[dict[str, Any]]:
        path = self.dir / "corrections.log"
        if not path.exists():
            return []
        lines = path.read_text().strip().splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    # ------------------------------------------------------------------
    # peers.json
    # ------------------------------------------------------------------

    def read_peers(self) -> list[dict[str, Any]]:
        path = self.dir / "peers.json"
        if not path.exists():
            return []
        return json.loads(path.read_text())

    def write_peers(self, peers: list[dict[str, Any]]) -> None:
        (self.dir / "peers.json").write_text(json.dumps(peers, indent=2))

    def upsert_peer(self, peer: dict[str, Any]) -> None:
        """Agrega o actualiza un peer por DID."""
        peers = self.read_peers()
        for i, p in enumerate(peers):
            if p.get("did") == peer.get("did"):
                peers[i] = {**p, **peer}
                self.write_peers(peers)
                return
        peers.append(peer)
        self.write_peers(peers)

    # ------------------------------------------------------------------
    # budget.json
    # ------------------------------------------------------------------

    def read_budget(self) -> dict[str, Any]:
        path = self.dir / "budget.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text())

    def write_budget(self, data: dict[str, Any]) -> None:
        (self.dir / "budget.json").write_text(json.dumps(data, indent=2))

    def record_usage(self, tokens_used: int) -> None:
        """Registra uso de tokens en budget.json."""
        budget = self.read_budget()
        budget["used_tokens"] = budget.get("used_tokens", 0) + tokens_used
        budget["calls_total"] = budget.get("calls_total", 0) + 1
        self.write_budget(budget)

    def is_over_budget(self) -> bool:
        budget = self.read_budget()
        limit = budget.get("monthly_limit_tokens", 500_000)
        used = budget.get("used_tokens", 0)
        return used >= limit

    # ------------------------------------------------------------------
    # threads/
    # ------------------------------------------------------------------

    def thread_path(self, thread_id: str) -> Path:
        return self.dir / "threads" / f"{thread_id}.json"

    def read_thread(self, thread_id: str) -> list[dict[str, Any]]:
        path = self.thread_path(thread_id)
        if not path.exists():
            return []
        return json.loads(path.read_text())

    def write_thread(self, thread_id: str, messages: list[dict[str, Any]]) -> None:
        self.thread_path(thread_id).write_text(json.dumps(messages, indent=2))

    def append_to_thread(self, thread_id: str, message: dict[str, Any]) -> None:
        messages = self.read_thread(thread_id)
        messages.append(message)
        self.write_thread(thread_id, messages)

    def list_threads(self) -> list[str]:
        threads_dir = self.dir / "threads"
        if not threads_dir.exists():
            return []
        return [p.stem for p in threads_dir.glob("*.json")]
