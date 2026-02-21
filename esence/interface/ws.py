"""
esence/interface/ws.py — WebSocket handler para la UI local
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, TYPE_CHECKING

from fastapi import WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from esence.core.node import EsenceNode

logger = logging.getLogger(__name__)


class WSManager:
    """Gestiona conexiones WebSocket activas y broadcast de eventos."""

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._node: "EsenceNode | None" = None

    def set_node(self, node: "EsenceNode") -> None:
        self._node = node

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info(f"WS connected ({len(self._connections)} total)")
        # Enviar estado inicial
        await self._send_to(ws, "node_state", await self._build_state())

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info(f"WS disconnected ({len(self._connections)} total)")

    async def broadcast(self, event_type: str, data: Any) -> None:
        """Envía un evento a todas las conexiones activas."""
        if not self._connections:
            return
        payload = json.dumps({"type": event_type, "data": data})
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def _send_to(self, ws: WebSocket, event_type: str, data: Any) -> None:
        try:
            await ws.send_text(json.dumps({"type": event_type, "data": data}))
        except Exception as e:
            logger.error(f"Error sending to WS: {e}")

    async def _build_state(self) -> dict:
        """Construye el estado del nodo para enviarlo al cliente."""
        if not self._node:
            return {"status": "initializing"}
        return self._node.get_state()

    async def handle(self, ws: WebSocket) -> None:
        """Loop principal de un WebSocket — recibe mensajes del dueño."""
        await self.connect(ws)
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                    await self._handle_client_message(ws, msg)
                except json.JSONDecodeError:
                    await self._send_to(ws, "error", {"message": "JSON inválido"})
        except WebSocketDisconnect:
            self.disconnect(ws)

    async def _handle_client_message(self, ws: WebSocket, msg: dict) -> None:
        """Procesa mensajes entrantes del dueño desde la UI."""
        if not self._node:
            return

        msg_type = msg.get("type")

        if msg_type == "chat":
            # El dueño habla con su propio agente
            content = msg.get("content", "")
            if content:
                response = await self._node.engine.generate_self_response(content)
                await self._send_to(ws, "agent_reply", {
                    "content": response,
                    "source": "self",
                })

        elif msg_type == "approve":
            # Aprueba un mensaje pendiente (opcionalmente con reply editada)
            thread_id = msg.get("thread_id")
            edited_reply = msg.get("edited_reply")  # None si no hay edición
            if thread_id:
                approved = await self._node.queue.approve(thread_id, edited_reply=edited_reply)
                if approved:
                    await self._send_to(ws, "approved", {"thread_id": thread_id})

        elif msg_type == "reject":
            # Rechaza un mensaje pendiente
            thread_id = msg.get("thread_id")
            if thread_id:
                await self._node.queue.reject(thread_id)
                await self._send_to(ws, "rejected", {"thread_id": thread_id})

        elif msg_type == "get_state":
            await self._send_to(ws, "node_state", await self._build_state())

        elif msg_type == "get_pending":
            pending = await self._node.queue.peek_pending()
            await self._send_to(ws, "pending_messages", {"messages": pending})

        elif msg_type == "set_mood":
            mood = msg.get("mood")
            if mood:
                try:
                    self._node.store.set_mood(mood)
                    await self._send_to(ws, "mood_changed", {"mood": mood})
                    await self._send_to(ws, "node_state", await self._build_state())
                except ValueError as e:
                    await self._send_to(ws, "error", {"message": str(e)})

        else:
            await self._send_to(ws, "error", {"message": f"Tipo desconocido: {msg_type}"})


# Singleton
ws_manager = WSManager()
