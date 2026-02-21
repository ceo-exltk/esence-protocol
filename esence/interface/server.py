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
    async def approve_message(thread_id: str) -> JSONResponse:
        """Aprueba un mensaje pendiente."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        approved = await node.queue.approve(thread_id)
        if not approved:
            raise HTTPException(status_code=404, detail="Mensaje no encontrado")
        await ws_manager.broadcast("approved", {"thread_id": thread_id})
        return JSONResponse({"status": "approved", "thread_id": thread_id})

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
        return FileResponse(str(index))

    return app
