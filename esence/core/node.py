"""
esence/core/node.py — Proceso principal del nodo Esence

Runnable como: python3 -m esence.core.node
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import uvicorn

from esence.config import config
from esence.core.identity import Identity
from esence.core.queue import MessageQueue
from esence.essence.engine import EssenceEngine
from esence.essence.maturity import calculate_maturity, maturity_label
from esence.essence.store import EssenceStore
from esence.protocol.message import MessageStatus, MessageType, PeerIntro
from esence.protocol.peers import PeerManager
from esence.protocol.transport import send_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class EsenceNode:
    """Nodo Esence — orquesta todos los subsistemas."""

    def __init__(self):
        self.store = EssenceStore()
        self.identity: Identity | None = None
        self.queue = MessageQueue(self.store)
        self.engine = EssenceEngine(self.store)
        self.peers = PeerManager(self.store)
        self._running = False

    # ------------------------------------------------------------------
    # Arranque
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Inicializa el nodo y arranca todos los loops."""
        logger.info(f"Arrancando Esence Node — {config.did()}")

        # Validar configuración
        errors = config.validate()
        if errors:
            for e in errors:
                logger.warning(f"Config: {e}")

        # Cargar identidad
        if not config.essence_store_dir.exists():
            logger.warning(
                "essence-store/ no existe. Ejecutá ./setup.sh primero."
            )
            self._create_minimal_store()

        self.identity = Identity.load_or_generate()
        logger.info(f"Identidad: {self.identity.did}")

        # Restaurar mensajes pendientes
        self.queue.restore_pending()
        pending = self.queue.pending_count()
        if pending:
            logger.info(f"Mensajes pendientes restaurados: {pending}")

        # Suscribir queue a ws_manager para broadcast en tiempo real
        from esence.interface.ws import ws_manager
        self.queue.subscribe(self._on_queue_event)

        self._running = True
        logger.info(f"Interfaz en http://localhost:{config.port}")

        # Bootstrap: conectar con peer inicial si está configurado
        if config.bootstrap_peer:
            asyncio.create_task(self._bootstrap_peer(config.bootstrap_peer))

        # Lanzar tareas concurrentes
        await asyncio.gather(
            self._run_http_server(),
            self._process_inbound_loop(),
            self._process_outbound_loop(),
            self._gossip_loop(),
        )

    def _create_minimal_store(self) -> None:
        """Crea un essence-store mínimo si no existe (para desarrollo)."""
        identity_data = {
            "id": config.did(),
            "name": config.node_name,
            "domain": config.domain,
            "languages": ["es"],
            "values": [],
        }
        self.store.initialize(identity_data)
        identity = Identity.generate(config.node_name, config.domain)
        identity.save()
        logger.info("essence-store/ creado automáticamente")

    # ------------------------------------------------------------------
    # HTTP Server
    # ------------------------------------------------------------------

    async def _run_http_server(self) -> None:
        from esence.interface.server import create_app
        app = create_app(node=self)

        server_config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=config.port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(server_config)
        await server.serve()

    # ------------------------------------------------------------------
    # Loops de procesamiento
    # ------------------------------------------------------------------

    async def _process_inbound_loop(self) -> None:
        """Procesa mensajes inbound: genera respuesta propuesta y notifica la UI."""
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self.queue.dequeue_inbound(), timeout=1.0
                )
                asyncio.create_task(self._handle_inbound(message))
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error en inbound loop: {e}")

    async def _handle_inbound(self, message: dict[str, Any]) -> None:
        """Procesa un mensaje inbound: genera respuesta propuesta."""
        from esence.interface.ws import ws_manager

        sender_did = message.get("from_did", "")
        content = message.get("content", "")
        thread_id = message.get("thread_id", "")
        msg_type = message.get("type", "")

        logger.info(f"Mensaje inbound de {sender_did[:40]}… (tipo: {msg_type})")

        # Manejar PeerIntro — actualizar lista de peers por gossip
        if msg_type == MessageType.PEER_INTRO:
            known_peers = message.get("known_peers", [])
            new_count = self.peers.merge_gossip(known_peers, sender_did)
            if new_count:
                logger.info(f"Gossip: {new_count} nuevos peers de {sender_did[:40]}…")
            self.peers.record_interaction(sender_did, successful=True)
            return

        # Registrar interacción con el peer
        self.peers.record_interaction(sender_did, successful=True)

        # Generar respuesta propuesta con el engine
        try:
            proposed = await self.engine.generate(
                user_message=content,
                max_tokens=512,
            )
            # Agregar propuesta al mensaje
            message["proposed_reply"] = proposed

            # Actualizar en el store
            messages = self.store.read_thread(thread_id)
            for m in messages:
                if m.get("thread_id") == thread_id:
                    m["proposed_reply"] = proposed
            self.store.write_thread(thread_id, messages)

            # Si el mensaje es auto_approved → aprobar sin revisión humana
            if message.get("status") == MessageStatus.AUTO_APPROVED:
                logger.info(f"Auto-aprobando respuesta para {thread_id[:8]}…")
                await self.queue.approve(thread_id)
                await ws_manager.broadcast("auto_approved", {
                    "thread_id": thread_id,
                    "proposed_reply": proposed,
                })
            else:
                # Notificar UI para revisión humana
                await ws_manager.broadcast("review_ready", {
                    "thread_id": thread_id,
                    "proposed_reply": proposed,
                    "message": message,
                })

        except Exception as e:
            logger.error(f"Error generando respuesta propuesta: {e}")

    async def _process_outbound_loop(self) -> None:
        """Envía mensajes outbound aprobados."""
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self.queue.dequeue_outbound(), timeout=1.0
                )
                asyncio.create_task(self._send_outbound(message))
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error en outbound loop: {e}")

    async def _send_outbound(self, message: dict[str, Any]) -> None:
        """Envía un mensaje outbound firmado."""
        from esence.protocol.message import parse_message

        try:
            esence_msg = parse_message(message)
            if self.identity:
                success = await send_message(esence_msg, self.identity)
                thread_id = message.get("thread_id", "")
                status = MessageStatus.SENT if success else MessageStatus.PENDING_HUMAN_REVIEW
                await self.queue.mark_status(thread_id, status)

                if success:
                    self.peers.record_interaction(
                        message.get("to_did", ""), successful=True
                    )
                    logger.info(f"Mensaje enviado a {message.get('to_did', '')[:40]}…")
        except Exception as e:
            logger.error(f"Error enviando mensaje outbound: {e}")

    # ------------------------------------------------------------------
    # Queue event handler (para broadcast WS)
    # ------------------------------------------------------------------

    async def _on_queue_event(self, event_type: str, data: dict) -> None:
        from esence.interface.ws import ws_manager
        await ws_manager.broadcast(event_type, data)

        # Disparar extracción de patrones cada 5 correcciones
        if event_type == "correction_logged":
            count = data.get("count", 0)
            if count > 0 and count % 5 == 0:
                asyncio.create_task(self._run_pattern_extraction())

    async def _run_pattern_extraction(self) -> None:
        """Extrae patrones en background después de cada 5 correcciones."""
        from esence.essence.patterns import extract_patterns
        try:
            added = await extract_patterns(self.store, self.engine)
            if added:
                logger.info(f"Extracción de patrones completada: {added} nuevos patrones")
                from esence.interface.ws import ws_manager
                await ws_manager.broadcast("patterns_updated", {"new_patterns": added})
        except Exception as e:
            logger.error(f"Error en extracción de patrones: {e}")

    # ------------------------------------------------------------------
    # Estado del nodo (para la UI)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Gossip loop
    # ------------------------------------------------------------------

    async def _gossip_loop(self) -> None:
        """Envía PeerIntro a peers de confianza cada 5 minutos."""
        while self._running:
            await asyncio.sleep(300)  # 5 min
            try:
                await self._send_gossip()
            except Exception as e:
                logger.error(f"Error en gossip loop: {e}")

    async def _send_gossip(self) -> None:
        """Envía PeerIntro con known_peers a todos los peers de confianza."""
        if not self.identity:
            return
        trusted = self.peers.trusted_peers(min_trust=0.4)
        if not trusted:
            return
        known_peers = self.peers.get_gossip_payload()
        for peer in trusted:
            peer_did = peer.get("did", "")
            if not peer_did:
                continue
            msg = PeerIntro(
                from_did=self.identity.did,
                to_did=peer_did,
                content="peer_intro",
                known_peers=known_peers,
                public_key=self.identity.public_key_b64(),
            )
            try:
                await send_message(msg, self.identity)
                logger.debug(f"Gossip enviado a {peer_did[:40]}…")
            except Exception as e:
                logger.error(f"Error enviando gossip a {peer_did[:40]}: {e}")

    async def _bootstrap_peer(self, peer_did: str) -> None:
        """Envía PeerIntro al peer de bootstrap al arrancar."""
        if not self.identity:
            return
        logger.info(f"Bootstrap: conectando con {peer_did}")
        # Registrar el peer
        self.peers.add_or_update(peer_did, trust_score=0.3)
        msg = PeerIntro(
            from_did=self.identity.did,
            to_did=peer_did,
            content="peer_intro",
            known_peers=self.peers.get_gossip_payload(),
            public_key=self.identity.public_key_b64(),
        )
        try:
            await send_message(msg, self.identity)
            logger.info(f"Bootstrap PeerIntro enviado a {peer_did}")
        except Exception as e:
            logger.warning(f"Error en bootstrap con {peer_did}: {e}")

    # ------------------------------------------------------------------
    # Estado del nodo (para la UI)
    # ------------------------------------------------------------------

    def get_state(self) -> dict[str, Any]:
        """Retorna el estado actual del nodo para la UI."""
        from esence.essence.maturity import calculate_maturity, maturity_label

        budget = self.store.read_budget()
        maturity = calculate_maturity(self.store)

        corrections = self.store.read_corrections()
        patterns = self.store.read_patterns()

        return {
            "status": "online" if self._running else "offline",
            "did": self.identity.did if self.identity else config.did(),
            "node_name": config.node_name,
            "domain": config.domain,
            "peer_count": self.peers.peer_count(),
            "pending_count": self.queue.pending_count(),
            "mood": budget.get("mood", "moderate"),
            "budget": {
                "used_tokens": budget.get("used_tokens", 0),
                "monthly_limit_tokens": budget.get("monthly_limit_tokens", 500_000),
                "calls_total": budget.get("calls_total", 0),
            },
            "maturity": maturity,
            "maturity_label": maturity_label(maturity),
            "corrections_count": len(corrections),
            "patterns_count": len(patterns),
        }

    async def stop(self) -> None:
        self._running = False
        logger.info("Nodo detenido")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

async def main() -> None:
    node = EsenceNode()
    try:
        await node.start()
    except KeyboardInterrupt:
        await node.stop()
        logger.info("Hasta luego.")


if __name__ == "__main__":
    asyncio.run(main())
