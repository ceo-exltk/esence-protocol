# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Instalación rápida

Si acabás de clonar este repo, ejecutá el skill de setup:
```
/setup
```
Claude Code va a guiarte por todo el proceso automáticamente.

Para debug y preguntas sobre el código, el subagente `esense-dev` tiene contexto completo del protocolo.

---

# Esense Protocol — Node 0 (Genesis)

## Qué es esto

Esense es un protocolo P2P descentralizado donde cada persona instala un nodo que crea un agente digital que la representa. El agente aprende la esencia del dueño a través de la interacción (no configuración), y se comunica asincrónicamente con otros agentes de la red. No hay servidor central. No hay empresa dueña. El protocolo es el producto.

**Tagline**: "No compartís tu suscripción. Compartís quién sos."

Este repo es el **nodo genesis — Node 0**. El primer nodo de la red, equivalente al bloque genesis de Bitcoin.

---

## Estado de implementación

**Todo el código de aplicación está por implementarse.** Los directorios de módulos (`core/`, `essence/`, `protocol/`, `interface/`) existen pero solo contienen `__init__.py` vacíos. El punto de entrada `python3 -m esense.core.node` aún no funciona.

Fases completadas: **ninguna**. Empezar por Fase 1 — Identidad.

---

## Stack técnico

- **Python 3.11+** con asyncio
- **FastAPI** — servidor HTTP (endpoint ANP público + interfaz local)
- **Websockets** — comunicación en tiempo real con la UI
- **cryptography** (Python) — Ed25519 para identidad y firmas
- **anthropic** — AI provider por defecto
- **Interface** — página web en `localhost:7777` (HTML/CSS/JS vanilla)
- **Persistence** — archivos locales JSON + Markdown (sin base de datos)

---

## Desarrollo

### Setup inicial

```bash
cp .env.example .env          # configurar ANTHROPIC_API_KEY, ESENSE_NODE_NAME
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./setup.sh                    # genera identidad y essence-store/
```

### Arrancar el nodo

```bash
./start.sh                    # arranca y abre localhost:7777
# o directamente:
python3 -m esense.core.node
```

### Variables de entorno (`.env`)

| Variable | Descripción |
|---|---|
| `ANTHROPIC_API_KEY` | API key del proveedor AI |
| `ESENSE_NODE_NAME` | Nombre del nodo (parte del DID) |
| `ESENSE_DOMAIN` | Dominio (default: `localhost`) |
| `ESENSE_DONATION_PCT` | % de capacidad compartida con la red (default: 10) |
| `ESENSE_PORT` | Puerto de la interfaz (default: 7777) |

---

## Arquitectura

### Módulos

```
esense/
├── core/node.py        — proceso principal, event loop, orquesta todo
├── core/identity.py    — DID:WBA, Ed25519 key pair, firma/verificación
├── core/queue.py       — cola de mensajes inbound/outbound
├── essence/engine.py   — interfaz con AI provider, genera respuestas
├── essence/store.py    — lee/escribe el essence store
├── essence/maturity.py — calcula essence_maturity score
├── protocol/message.py — schema de mensajes ANP + extensiones Esense
├── protocol/transport.py — envío/recepción HTTPS entre nodos
├── protocol/peers.py   — gestión de peer list, gossip
├── interface/server.py — FastAPI: rutas ANP públicas + rutas locales UI
├── interface/ws.py     — websocket handler para la UI
└── interface/static/   — HTML + CSS + JS de localhost:7777
```

### Essence Store (`essence-store/` — ignorado por git)

Creado por `setup.sh`. Todos los archivos son JSON o Markdown planos, editables a mano.

| Archivo | Contenido |
|---|---|
| `identity.json` | DID, nombre, dominio, languages, values |
| `patterns.json` | Patrones de razonamiento extraídos de corrections.log |
| `context.md` | Conocimiento acumulado del dueño en sus dominios |
| `corrections.log` | JSONL — una línea por corrección del dueño |
| `peers.json` | Lista de peers conocidos con trust score |
| `budget.json` | Límites de gasto AI y configuración de autonomía |
| `threads/` | Hilos de conversación con otros nodos |

### Protocolo de mensajes (Esense over ANP)

```json
{
  "esense_version": "0.2",
  "type": "thread_message | thread_reply | peer_intro | capacity_status",
  "thread_id": "uuid",
  "from_did": "did:wba:sender.com:alice",
  "to_did": "did:wba:receiver.com:bob",
  "content": "...",
  "status": "pending_human_review | approved | sent | answered | rejected",
  "timestamp": "ISO8601",
  "signature": "Ed25519"
}
```

### Identidad — DID:WBA

```
did:wba:yourdomain.com:yourname
→ resuelve a: https://yourdomain.com/.well-known/did.json
```

MVP local: `did:wba:localhost:node0` con did.json servido en `localhost:7777/.well-known/did.json`

---

## Fases de implementación

### Fase 1 — Identidad ← EMPEZAR AQUÍ
- [ ] Generar Ed25519 key pair
- [ ] Crear DID:WBA local
- [ ] Generar y servir did.json
- [ ] Firmar mensajes salientes
- [ ] Verificar firmas entrantes

### Fase 2 — Essence Store
- [ ] Crear estructura de archivos en setup
- [ ] Leer/escribir corrections.log
- [ ] Leer/escribir patterns.json
- [ ] Calcular essence_maturity
- [ ] Cargar contexto completo para el AI provider

### Fase 3 — Nodo + API
- [ ] FastAPI server con rutas ANP públicas
- [ ] Cola de mensajes inbound/outbound
- [ ] Capacity manager con budget enforcement
- [ ] Peer manager con gossip básico

### Fase 4 — Interfaz
- [ ] localhost:7777 con websocket
- [ ] Feed de mensajes del agente
- [ ] Review card para mensajes pendientes
- [ ] Input para hablar con el propio agente

---

## Principios que no se negocian

1. **Sin base de datos externa** — todo en archivos locales
2. **Sin servidor central** — el nodo es soberano
3. **Essence store siempre legible** — JSON y Markdown planos, editables a mano
4. **Nada sale sin firma** — todo mensaje outbound lleva Ed25519
5. **Esencia emerge, no se configura** — el dueño nunca declara quién es
6. **Humano en el loop** — el agente consulta antes de responder por defecto
7. **Sharing implícito** — la capacidad se comparte como consecuencia de existir, no como donación explícita

---

## Contexto de sesión

Al arrancar una sesión nueva, indicar:
> "Leé el CLAUDE.md y continuemos con [Fase X — descripción]. El estado actual es: [qué está hecho]."
