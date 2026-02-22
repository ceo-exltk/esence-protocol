"""
esense/interface/server.py — FastAPI app: rutas ANP públicas + UI local
"""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any, TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from esense.config import config
from esense.interface.ws import ws_manager

if TYPE_CHECKING:
    from esense.core.node import EsenseNode

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

# Rate limiting — in-memory por IP
_rate_limit: dict[str, list[float]] = defaultdict(list)
_RATE_WINDOW = 60   # segundos
_RATE_MAX = 30      # mensajes por ventana por IP


def create_app(node: "EsenseNode | None" = None) -> FastAPI:
    """Crea y configura la FastAPI app."""

    app = FastAPI(
        title="Esense Node",
        description="Esense Protocol — P2P Agent Node",
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
        from esense.protocol.transport import receive_message

        # Rate limiting por IP
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        _rate_limit[client_ip] = [t for t in _rate_limit[client_ip] if now - t < _RATE_WINDOW]
        if len(_rate_limit[client_ip]) >= _RATE_MAX:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        _rate_limit[client_ip].append(now)

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
        from esense.protocol.transport import send_message
        from esense.protocol.message import EsenseMessage, MessageType, MessageStatus
        import uuid
        msg = EsenseMessage(
            type=MessageType.THREAD_MESSAGE,
            thread_id=str(uuid.uuid4()),
            from_did=node.identity.did,
            to_did=to_did,
            content=content,
            status=MessageStatus.SENT,
        )
        success = await send_message(msg, node.identity)
        return JSONResponse({"status": "sent" if success else "failed"})

    @app.get("/api/peers")
    async def get_peers() -> JSONResponse:
        """Lista de peers conocidos, enriquecida con display_name."""
        if not node:
            return JSONResponse([])
        peers = node.peers.get_all()
        for peer in peers:
            peer["display_name"] = node.peers.get_peer_display_name(peer.get("did", ""))
        return JSONResponse(peers)

    @app.post("/api/peers")
    async def add_peer(request: Request) -> JSONResponse:
        """Agrega un peer por DID. Acepta alias opcional."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="JSON inválido")
        did = body.get("did")
        if not did:
            raise HTTPException(status_code=400, detail="did requerido")
        alias = body.get("alias") or None
        peer = node.peers.add_or_update(did, trust_score=0.3, alias=alias)
        peer["display_name"] = node.peers.get_peer_display_name(did)
        return JSONResponse({"status": "ok", "peer": peer})

    @app.patch("/api/peers/{did:path}")
    async def update_peer_alias(did: str, request: Request) -> JSONResponse:
        """Actualiza el alias de un peer."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        decoded_did = urllib.parse.unquote(did)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="JSON inválido")
        alias = body.get("alias", "").strip() or None
        peer = node.peers.add_or_update(decoded_did, alias=alias)
        peer["display_name"] = node.peers.get_peer_display_name(decoded_did)
        return JSONResponse({"status": "ok", "peer": peer})

    @app.delete("/api/peers/{did:path}")
    async def delete_peer(did: str) -> JSONResponse:
        """Elimina un peer por DID."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        decoded_did = urllib.parse.unquote(did)
        node.peers.remove(decoded_did)
        return JSONResponse({"status": "ok", "did": decoded_did})

    @app.post("/api/peers/{did:path}/block")
    async def block_peer(did: str, request: Request) -> JSONResponse:
        """Bloquea o desbloquea un peer."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        decoded_did = urllib.parse.unquote(did)
        try:
            body = await request.json()
            blocked = bool(body.get("blocked", True))
        except Exception:
            blocked = True
        peer = node.peers.add_or_update(decoded_did, blocked=blocked)
        peer["display_name"] = node.peers.get_peer_display_name(decoded_did)
        await ws_manager.broadcast("peer_blocked", {"did": decoded_did, "blocked": blocked})
        return JSONResponse({"status": "ok", "peer": peer})

    @app.delete("/api/threads/{thread_id}")
    async def delete_thread(thread_id: str) -> JSONResponse:
        """Elimina un thread del essence-store."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        # Sacar de la cola de pendientes si estuviera
        node.queue._pending.pop(thread_id, None)
        deleted = node.store.delete_thread(thread_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Thread no encontrado")
        return JSONResponse({"status": "ok", "thread_id": thread_id})

    @app.get("/api/health")
    async def health() -> JSONResponse:
        """Estado de salud del nodo."""
        if not node:
            return JSONResponse({"status": "initializing"}, status_code=503)
        from esense.essence.maturity import calculate_maturity
        over_budget = node.store.is_over_budget()
        budget = node.store.read_budget()
        peers = node.peers.get_all()
        last_activity = max(
            (p.get("last_seen", "") or "" for p in peers),
            default=None,
        ) or None
        return JSONResponse({
            "status": "healthy" if not over_budget else "degraded",
            "did": node.identity.did if node.identity else config.did(),
            "peer_count": node.peers.peer_count(),
            "pending_count": node.queue.pending_count(),
            "maturity": calculate_maturity(node.store),
            "budget": {
                "used_tokens": budget.get("used_tokens", 0),
                "monthly_limit_tokens": budget.get("monthly_limit_tokens", 500_000),
                "over_budget": over_budget,
            },
            "last_peer_activity": last_activity,
            "public_url": config.public_url or None,
            "version": "0.2.0",
        })

    @app.get("/api/threads")
    async def list_threads() -> JSONResponse:
        """Lista de threads recientes con metadata."""
        if not node:
            return JSONResponse([])
        return JSONResponse(node.get_recent_threads(limit=20))

    @app.get("/api/threads/{thread_id}")
    async def get_thread(thread_id: str) -> JSONResponse:
        """Mensajes completos de un thread."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        messages = node.store.read_thread(thread_id)
        if not messages:
            raise HTTPException(status_code=404, detail="Thread no encontrado")
        return JSONResponse(messages)

    @app.get("/api/context")
    async def get_context() -> JSONResponse:
        """Retorna el contenido de context.md."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        content = node.store.read_context()
        return JSONResponse({"content": content})

    @app.post("/api/context")
    async def save_context(request: Request) -> JSONResponse:
        """Actualiza context.md."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="JSON inválido")
        content = body.get("content")
        if content is None:
            raise HTTPException(status_code=400, detail="content requerido")
        node.store.write_context(content)
        return JSONResponse({"status": "ok"})

    @app.get("/api/patterns")
    async def get_patterns() -> JSONResponse:
        """Retorna los patrones extraídos."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        patterns = node.store.read_patterns()
        return JSONResponse(patterns)

    @app.get("/api/auto-approve")
    async def get_auto_approve() -> JSONResponse:
        """Estado actual del toggle de auto-aprobación."""
        if not node:
            return JSONResponse({"auto_approve": False})
        return JSONResponse({"auto_approve": node.store.get_auto_approve()})

    @app.post("/api/auto-approve")
    async def set_auto_approve(request: Request) -> JSONResponse:
        """Activa o desactiva la auto-aprobación."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        try:
            body = await request.json()
            enabled = bool(body.get("enabled", False))
        except Exception:
            raise HTTPException(status_code=400, detail="JSON inválido")
        node.store.set_auto_approve(enabled)
        await ws_manager.broadcast("auto_approve_changed", {"enabled": enabled})
        return JSONResponse({"status": "ok", "auto_approve": enabled})

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
        from esense.essence.maturity import calculate_maturity, maturity_label
        from esense.essence.store import EssenceStore
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
            return HTMLResponse("<h1>Esense Node</h1><p>UI not found</p>")
        return FileResponse(str(index), headers={"Cache-Control": "no-cache"})

    return app
