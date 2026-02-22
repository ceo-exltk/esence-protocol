"""
esense/core/queue.py — Cola asyncio inbound/outbound con persistencia en threads/
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

from esense.config import config
from esense.essence.store import EssenceStore
from esense.protocol.message import EsenseMessage, MessageStatus


class MessageQueue:
    """
    Cola de mensajes con dos canales: inbound y outbound.

    - inbound: mensajes recibidos de otros nodos, esperan revisión humana
    - outbound: mensajes a enviar, generados por el agente o aprobados por el dueño
    """

    def __init__(self, store: EssenceStore | None = None):
        self.store = store or EssenceStore()
        self._inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._pending: dict[str, dict[str, Any]] = {}  # thread_id → message
        self._subscribers: list[Callable[[str, dict], Awaitable[None]]] = []

    # ------------------------------------------------------------------
    # Suscripción a eventos
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable[[str, dict], Awaitable[None]]) -> None:
        """Registra un callback async que se llama con (event_type, data)."""
        self._subscribers.append(callback)

    async def _emit(self, event_type: str, data: dict) -> None:
        for cb in self._subscribers:
            try:
                await cb(event_type, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Inbound
    # ------------------------------------------------------------------

    async def enqueue_inbound(self, message: dict[str, Any]) -> None:
        """Recibe un mensaje entrante. El mood de disponibilidad define el routing."""
        from esense.essence.maturity import calculate_maturity

        thread_id = message.get("thread_id", str(uuid.uuid4()))
        message["thread_id"] = thread_id

        mood = self.store.get_mood()
        from_did = message.get("from_did", "")

        # Trust del remitente
        peers = self.store.read_peers()
        sender_peer = next((p for p in peers if p.get("did") == from_did), None)
        peer_trust = sender_peer.get("trust_score", 0.0) if sender_peer else 0.0

        # Peer bloqueado → rechazar siempre, sin importar mood
        if sender_peer and sender_peer.get("blocked"):
            message["status"] = MessageStatus.REJECTED
            self.store.append_to_thread(thread_id, message)
            await self._emit("rejected", {"thread_id": thread_id})
            return

        # Routing por mood
        # dnd → rechazar inmediatamente, ignorar auto_approve
        if mood == "dnd":
            message["status"] = MessageStatus.REJECTED
            self.store.append_to_thread(thread_id, message)
            await self._emit("rejected", {"thread_id": thread_id})
            return

        # Auto-approve global (toggle del usuario) — ignora mood/maturity
        if self.store.get_auto_approve():
            status = MessageStatus.AUTO_APPROVED

        # available → auto-aprobar si trust mínimo
        elif mood == "available" and peer_trust >= 0.3:
            status = MessageStatus.AUTO_APPROVED

        # moderate → auto-aprobar con madurez + trust alto
        elif mood == "moderate":
            maturity = calculate_maturity(self.store)
            budget = self.store.read_budget()
            threshold = budget.get("autonomy_threshold", 0.6)
            if maturity >= threshold and peer_trust >= 0.5:
                status = MessageStatus.AUTO_APPROVED
            else:
                status = MessageStatus.PENDING_HUMAN_REVIEW

        # absent → siempre pending, el dueño revisa cuando vuelve
        else:
            status = MessageStatus.PENDING_HUMAN_REVIEW

        message["status"] = status

        # Persistir en threads/
        self.store.append_to_thread(thread_id, message)
        self._pending[thread_id] = message

        await self._inbound.put(message)
        await self._emit("inbound_message", message)

    async def dequeue_inbound(self) -> dict[str, Any]:
        """Espera y retorna el próximo mensaje inbound."""
        return await self._inbound.get()

    async def peek_pending(self) -> list[dict[str, Any]]:
        """Retorna todos los mensajes pendientes de revisión."""
        return [
            m for m in self._pending.values()
            if m.get("status") == MessageStatus.PENDING_HUMAN_REVIEW
        ]

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def enqueue_outbound(self, message: dict[str, Any]) -> None:
        """Agrega un mensaje a la cola de salida."""
        thread_id = message.get("thread_id", str(uuid.uuid4()))
        message["thread_id"] = thread_id
        self.store.append_to_thread(thread_id, message)
        await self._outbound.put(message)
        await self._emit("outbound_queued", message)

    async def dequeue_outbound(self) -> dict[str, Any]:
        """Espera y retorna el próximo mensaje outbound para enviar."""
        return await self._outbound.get()

    # ------------------------------------------------------------------
    # Gestión de status
    # ------------------------------------------------------------------

    async def mark_status(self, thread_id: str, status: MessageStatus) -> None:
        """Actualiza el status de un mensaje en memoria y en disco."""
        if thread_id in self._pending:
            self._pending[thread_id]["status"] = status

        messages = self.store.read_thread(thread_id)
        for msg in messages:
            if msg.get("thread_id") == thread_id:
                msg["status"] = status
        self.store.write_thread(thread_id, messages)

        await self._emit("status_changed", {"thread_id": thread_id, "status": status})

    async def approve(self, thread_id: str, edited_reply: str | None = None) -> dict[str, Any] | None:
        """Aprueba un mensaje pendiente y lo mueve a outbound.

        Si edited_reply difiere de proposed_reply, registra la corrección en corrections.log.
        """
        if thread_id not in self._pending:
            return None
        message = self._pending.pop(thread_id)
        proposed_reply = message.get("proposed_reply", "")

        # Determinar reply final
        final_reply = edited_reply if edited_reply is not None else proposed_reply

        # Registrar corrección (siempre — aprobación implícita o con edición)
        if proposed_reply:
            correction = {
                "original": proposed_reply,
                "edited": final_reply,
                "thread_id": thread_id,
                "from_did": message.get("from_did", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.store.append_correction(correction)

            # Notificar para trigger de extracción de patrones
            corrections = self.store.read_corrections()
            await self._emit("correction_logged", {
                "count": len(corrections),
                "thread_id": thread_id,
            })

        # Actualizar contenido del mensaje con la reply aprobada
        if final_reply:
            message["content"] = final_reply

        message["status"] = MessageStatus.APPROVED
        await self.mark_status(thread_id, MessageStatus.APPROVED)
        await self.enqueue_outbound(message)
        return message

    async def reject(self, thread_id: str) -> None:
        """Rechaza un mensaje pendiente."""
        if thread_id in self._pending:
            self._pending.pop(thread_id)
        await self.mark_status(thread_id, MessageStatus.REJECTED)

    # ------------------------------------------------------------------
    # Recuperación desde disco (al arrancar)
    # ------------------------------------------------------------------

    def restore_pending(self) -> None:
        """Recarga mensajes pendientes desde threads/ al arrancar el nodo."""
        for thread_id in self.store.list_threads():
            messages = self.store.read_thread(thread_id)
            if not messages:
                continue
            last = messages[-1]
            if last.get("status") == MessageStatus.PENDING_HUMAN_REVIEW:
                self._pending[thread_id] = last

    def qsize_inbound(self) -> int:
        return self._inbound.qsize()

    def qsize_outbound(self) -> int:
        return self._outbound.qsize()

    def get_pending(self, thread_id: str) -> dict[str, Any] | None:
        """Retorna un mensaje pendiente sin sacarlo de la cola."""
        return self._pending.get(thread_id)

    def pending_count(self) -> int:
        return len(self._pending)
