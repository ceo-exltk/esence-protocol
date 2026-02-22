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
        """Elimina un thread del essence-store y de la cola de pendientes."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        node.queue.remove_pending(thread_id)
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

    @app.get("/api/onboarding")
    async def get_onboarding() -> JSONResponse:
        """Estado del onboarding."""
        if not node:
            return JSONResponse({"complete": False})
        return JSONResponse({"complete": node.store.is_onboarding_complete()})

    @app.post("/api/onboarding/complete")
    async def complete_onboarding(request: Request) -> JSONResponse:
        """Guarda las respuestas del wizard en context.md y marca onboarding completo."""
        if not node:
            raise HTTPException(status_code=503, detail="Nodo no inicializado")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="JSON inválido")

        answers = body.get("answers", {})
        identity_name = node.identity.did.split(":")[-1] if node.identity else "vos"

        sections = []
        if answers.get("identity"):
            sections.append(f"# Quién soy\n{answers['identity'].strip()}")
        if answers.get("style"):
            sections.append(f"# Estilo de comunicación\n{answers['style'].strip()}")
        if answers.get("topics"):
            sections.append(f"# Temas y expertise\n{answers['topics'].strip()}")
        if answers.get("requests"):
            sections.append(f"# Cómo respondo ante pedidos\n{answers['requests'].strip()}")
        if answers.get("limits"):
            sections.append(f"# Lo que no respondo\n{answers['limits'].strip()}")
        if answers.get("notes"):
            sections.append(f"# Notas adicionales\n{answers['notes'].strip()}")

        context = "\n\n".join(sections)
        node.store.write_context(context)
        node.store.set_onboarding_complete()
        await ws_manager.broadcast("onboarding_complete", {})
        return JSONResponse({"status": "ok"})

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
    # Perfil público
    # ------------------------------------------------------------------

    @app.get("/@{name}", response_class=HTMLResponse)
    async def public_profile(name: str, request: Request) -> HTMLResponse:
        """Página pública del nodo — shareable como invite link."""
        if not node:
            return HTMLResponse(_profile_html_offline(name), status_code=503)

        state = node.get_state()
        did = state.get("did", config.did())
        node_name = state.get("node_name", name)
        mood = state.get("mood", "moderate")
        maturity_pct = round(state.get("maturity", 0) * 100)
        maturity_lbl = state.get("maturity_label", "nascent")
        corrections = state.get("corrections_count", 0)
        answered = corrections  # proxy: cada corrección = respuesta enviada

        # Primera línea del context.md como bio
        context_raw = node.store.read_context() if node else ""
        bio = ""
        for line in context_raw.splitlines():
            line = line.strip().lstrip("#").strip()
            if line and not line.startswith("##"):
                bio = line[:160]
                break

        base_url = str(request.base_url).rstrip("/")
        # Si hay ngrok, usar la URL pública
        if config.public_url:
            base_url = config.public_url.rstrip("/")

        return HTMLResponse(_profile_html(
            name=node_name,
            did=did,
            mood=mood,
            bio=bio,
            maturity_pct=maturity_pct,
            maturity_lbl=maturity_lbl,
            answered=answered,
            base_url=base_url,
        ))

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


# ---------------------------------------------------------------------------
# Profile page HTML generator
# ---------------------------------------------------------------------------

_MOOD_LABEL = {
    "available": ("●", "Disponible", "#00e676"),
    "moderate":  ("◑", "Moderado",   "#ffb300"),
    "absent":    ("○", "Ausente",    "#686868"),
    "dnd":       ("⊗", "No molestar","#ff5252"),
}


def _html_escape(s: str) -> str:
    return (str(s)
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _profile_html(
    name: str,
    did: str,
    mood: str,
    bio: str,
    maturity_pct: int,
    maturity_lbl: str,
    answered: int,
    base_url: str,
) -> str:
    mood_icon, mood_text, mood_color = _MOOD_LABEL.get(mood, ("●", mood, "#686868"))
    name_e  = _html_escape(name)
    did_e   = _html_escape(did)
    bio_e   = _html_escape(bio) if bio else "Agente Esense — representación digital de una persona real."
    lbl_e   = _html_escape(maturity_lbl)
    base_e  = _html_escape(base_url)
    anp_url = _html_escape(f"{base_url}/anp/message")

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>@{name_e} · esense</title>
  <meta property="og:title" content="@{name_e} en Esense">
  <meta property="og:description" content="{bio_e}">
  <style>
    :root {{
      --bg:#0d0d0d; --surface:#141414; --border:#272727;
      --text:#e8e8e8; --muted:#686868; --dim:#383838;
      --accent:#7c6af7; --green:#00e676; --font-mono:"SF Mono","Fira Code",monospace;
    }}
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px}}
    .card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:36px 40px;width:100%;max-width:480px;display:flex;flex-direction:column;gap:24px}}
    .logo{{font-family:var(--font-mono);font-size:12px;color:var(--muted);letter-spacing:1px;text-transform:uppercase}}
    .profile-header{{display:flex;align-items:center;gap:16px}}
    .avatar{{width:56px;height:56px;border-radius:50%;background:var(--accent);display:flex;align-items:center;justify-content:center;font-family:var(--font-mono);font-size:22px;font-weight:700;color:#fff;flex-shrink:0;border:2px solid var(--accent)}}
    .profile-info{{flex:1;min-width:0}}
    .profile-name{{font-size:20px;font-weight:700;color:var(--text)}}
    .profile-did{{font-family:var(--font-mono);font-size:10px;color:var(--muted);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .mood-badge{{display:inline-flex;align-items:center;gap:5px;font-size:12px;padding:3px 9px;border-radius:20px;border:1px solid var(--border);color:{mood_color};background:var(--bg);font-family:var(--font-mono);margin-top:6px}}
    .bio{{font-size:14px;color:var(--muted);line-height:1.6;border-left:2px solid var(--dim);padding-left:14px}}
    .stats{{display:flex;gap:24px}}
    .stat{{display:flex;flex-direction:column;gap:2px}}
    .stat-value{{font-family:var(--font-mono);font-size:18px;font-weight:700;color:var(--green)}}
    .stat-label{{font-size:11px;color:var(--muted)}}
    .maturity-wrap{{display:flex;flex-direction:column;gap:6px}}
    .maturity-row{{display:flex;justify-content:space-between;align-items:center}}
    .maturity-label{{font-family:var(--font-mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}}
    .maturity-val{{font-family:var(--font-mono);font-size:11px;color:var(--green)}}
    .bar{{height:4px;background:var(--dim);border-radius:2px;overflow:hidden}}
    .bar-fill{{height:100%;background:linear-gradient(90deg,#1b4332,var(--green));border-radius:2px}}
    .send-section{{display:flex;flex-direction:column;gap:10px}}
    .send-section h3{{font-family:var(--font-mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}}
    .did-copy{{display:flex;gap:8px;align-items:center}}
    .did-input{{flex:1;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);font-family:var(--font-mono);font-size:11px;padding:8px 10px;outline:none}}
    .btn-copy{{background:var(--accent);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:12px;font-weight:600;padding:8px 14px;white-space:nowrap;transition:opacity .15s}}
    .btn-copy:hover{{opacity:.85}}
    .divider{{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:11px}}
    .divider::before,.divider::after{{content:"";flex:1;height:1px;background:var(--border)}}
    .setup-hint{{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:14px;font-size:12px;color:var(--muted);line-height:1.6}}
    .setup-hint code{{font-family:var(--font-mono);font-size:11px;color:var(--green);background:#0f2a1a;padding:2px 6px;border-radius:3px}}
    .footer{{font-size:11px;color:var(--dim);text-align:center}}
    .footer a{{color:var(--muted);text-decoration:none}}
    .footer a:hover{{color:var(--text)}}
    #copied{{display:none;font-size:11px;color:var(--green);font-family:var(--font-mono)}}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">esense protocol</div>

    <div class="profile-header">
      <div class="avatar">{name_e[0].upper()}</div>
      <div class="profile-info">
        <div class="profile-name">@{name_e}</div>
        <div class="profile-did" title="{did_e}">{did_e}</div>
        <div class="mood-badge">{mood_icon} {mood_text}</div>
      </div>
    </div>

    <p class="bio">{bio_e}</p>

    <div class="stats">
      <div class="stat">
        <span class="stat-value">{answered}</span>
        <span class="stat-label">respuestas enviadas</span>
      </div>
      <div class="stat">
        <span class="stat-value">{maturity_pct}%</span>
        <span class="stat-label">esencia · {lbl_e}</span>
      </div>
    </div>

    <div class="maturity-wrap">
      <div class="maturity-row">
        <span class="maturity-label">Essence maturity</span>
        <span class="maturity-val">{lbl_e}</span>
      </div>
      <div class="bar"><div class="bar-fill" style="width:{maturity_pct}%"></div></div>
    </div>

    <div class="send-section">
      <h3>Enviarle un mensaje</h3>
      <div class="did-copy">
        <input class="did-input" id="did-val" value="{did_e}" readonly>
        <button class="btn-copy" onclick="copyDid()">Copiar DID</button>
      </div>
      <span id="copied">¡Copiado!</span>
      <div class="divider">tenés un nodo Esense</div>
      <p style="font-size:12px;color:var(--muted);line-height:1.6">
        Pegá el DID en el panel <strong>Enviar mensaje</strong> de tu nodo y escribí tu mensaje.
        Será revisado por <strong>@{name_e}</strong> antes de ser respondido.
      </p>
      <div class="divider">no tenés nodo</div>
      <div class="setup-hint">
        Para enviar un mensaje necesitás tu propio nodo Esense.<br><br>
        <strong>Instalar en 60 segundos:</strong><br>
        <code>git clone https://github.com/tu-repo/esense</code><br>
        <code>./setup.sh &amp;&amp; ./start.sh</code><br><br>
        O escribile directamente a <strong>@{name_e}</strong> en otra plataforma con tu DID.
      </div>
    </div>

    <div class="footer">
      Agente autónomo en la red <a href="https://esense.app">Esense Protocol</a> · v0.2
    </div>
  </div>

  <script>
    function copyDid() {{
      const val = document.getElementById('did-val').value;
      navigator.clipboard.writeText(val).then(() => {{
        const el = document.getElementById('copied');
        el.style.display = 'block';
        setTimeout(() => {{ el.style.display = 'none'; }}, 2000);
      }});
    }}
  </script>
</body>
</html>"""


def _profile_html_offline(name: str) -> str:
    name_e = _html_escape(name)
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>@{name_e} · esense</title>
<style>body{{background:#0d0d0d;color:#686868;font-family:monospace;display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center}}</style>
</head>
<body><p>@{name_e} está temporalmente offline.<br>Intentá de nuevo en unos minutos.</p></body>
</html>"""
