"""
esence/interface/server.py — FastAPI app: rutas ANP públicas + UI local
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from esence.config import config
from esence.interface.ws import ws_manager

if TYPE_CHECKING:
    from esence.core.node import EsenceNode

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def create_app(node: "EsenceNode | None" = None) -> FastAPI:
    """Crea y configura la FastAPI app."""

    app = FastAPI(
        title="Esence Node",
        description="Esence Protocol — P2P Agent Node",
        version="0.2.0",
        docs_url=None,
        redoc_url=None,
    )

    if node:
        ws_manager.set_node(node)

    # ------------------------------------------------------------------
    # Rutas ANP públicas
    # ------------------------------------------------------------------

    @app.post("/anp/message")
    async def receive_anp_message(request: Request) -> JSONResponse:
        """Recibe un mensaje ANP de otro nodo."""
        from esence.protocol.transport import receive_message

        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="JSON inválido")

        message, valid_sig = await receive_message(payload)

        if not valid_sig:
            if config.dev_skip_sig:
                logger.warning(f"[DEV] Firma omitida para {message.from_did}")
            else:
                logger.warning(f"Mensaje con firma inválida de {message.from_did}")
                raise HTTPException(status_code=401, detail="Firma inválida")

        if node:
            await node.queue.enqueue_inbound(message.model_dump())
            # Broadcast a la UI
            await ws_manager.broadcast("inbound_message", message.model_dump())

        return JSONResponse({"status": "received", "thread_id": message.thread_id})

    @app.get("/.well-known/did.json")
    async def get_did_document() -> JSONResponse:
        """Sirve el DID Document del nodo."""
        store_dir = config.essence_store_dir
        did_path = store_dir / "did.json"
        if not did_path.exists():
            raise HTTPException(status_code=404, detail="DID document no generado aún")
        return JSONResponse(json.loads(did_path.read_text()))

    # ------------------------------------------------------------------
    # Rutas locales UI
    # ------------------------------------------------------------------

    @app.get("/api/state")
    async def get_state() -> JSONResponse:
        """Estado actual del nodo."""
        if not node:
            return JSONResponse({"status": "initializing"})
        return JSONResponse(node.get_state())

    @app.get("/api/pending")
    async def get_pending() -> JSONResponse:
        """Mensajes pendientes de revisión."""
        if not node:
            return JSONResponse({"messages": []})
        pending = await node.queue.peek_pending()
        return JSONResponse({"messages": pending})

    @app.post("/api/approve/{thread_id}")
    async def approve_message(thread_id: str, request: Request) -> JSONResponse:
        """Aprueba un mensaje pendiente. Body JSON opcional: {"edited_reply": "..."}"""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        edited_reply: str | None = None
        try:
            body = await request.json()
            edited_reply = body.get("edited_reply") if isinstance(body, dict) else None
        except Exception:
            pass  # Body vacío o no JSON — OK, se aprueba sin edición
        approved = await node.queue.approve(thread_id, edited_reply=edited_reply)
        if not approved:
            raise HTTPException(status_code=404, detail="Mensaje no encontrado")
        await ws_manager.broadcast("approved", {"thread_id": thread_id})
        return JSONResponse({"status": "approved", "thread_id": thread_id})

    @app.post("/api/mood")
    async def set_mood(request: Request) -> JSONResponse:
        """Cambia el mood de disponibilidad: available | moderate | absent | dnd"""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        try:
            body = await request.json()
            mood = body.get("mood", "")
        except Exception:
            raise HTTPException(status_code=400, detail="JSON inválido")
        try:
            node.store.set_mood(mood)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        await ws_manager.broadcast("mood_changed", {"mood": mood})
        return JSONResponse({"status": "ok", "mood": mood})

    @app.post("/api/send")
    async def send_message_endpoint(request: Request) -> JSONResponse:
        """Envía un mensaje a otro nodo por DID."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="JSON inválido")
        to_did = body.get("to_did")
        content = body.get("content")
        if not to_did or not content:
            raise HTTPException(status_code=400, detail="to_did y content requeridos")
        from esence.protocol.transport import send_message
        from esence.protocol.message import EsenceMessage, MessageType, MessageStatus
        import uuid
        msg = EsenceMessage(
            type=MessageType.THREAD_MESSAGE,
            thread_id=str(uuid.uuid4()),
            from_did=node.identity.did,
            to_did=to_did,
            content=content,
            status=MessageStatus.SENT,
        )
        success = await send_message(msg, node.identity)
        return JSONResponse({"status": "sent" if success else "failed"})

    @app.post("/api/reject/{thread_id}")
    async def reject_message(thread_id: str) -> JSONResponse:
        """Rechaza un mensaje pendiente."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        await node.queue.reject(thread_id)
        await ws_manager.broadcast("rejected", {"thread_id": thread_id})
        return JSONResponse({"status": "rejected", "thread_id": thread_id})

    @app.get("/api/identity")
    async def get_identity() -> JSONResponse:
        """Identidad pública del nodo."""
        store_dir = config.essence_store_dir
        did_path = store_dir / "did.json"
        if not did_path.exists():
            raise HTTPException(status_code=404, detail="Identidad no generada")
        return JSONResponse(json.loads(did_path.read_text()))

    @app.get("/api/maturity")
    async def get_maturity() -> JSONResponse:
        """Essence maturity score."""
        from esence.essence.maturity import calculate_maturity, maturity_label
        from esence.essence.store import EssenceStore
        store = EssenceStore()
        score = calculate_maturity(store)
        return JSONResponse({"score": score, "label": maturity_label(score)})

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws_manager.handle(ws)

    # ------------------------------------------------------------------
    # Servir UI estática
    # ------------------------------------------------------------------

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def serve_ui() -> FileResponse:
        index = STATIC_DIR / "index.html"
        if not index.exists():
            return HTMLResponse("<h1>Esence Node</h1><p>UI not found</p>")
        return FileResponse(str(index), headers={"Cache-Control": "no-cache"})

    return app
