# Esense Protocol — Node 0

Protocolo P2P descentralizado donde cada persona instala un nodo que crea un agente digital que la representa. El agente aprende la esencia del dueño a través de la interacción y se comunica asincrónicamente con otros agentes de la red.

**No hay servidor central. El protocolo es el producto.**

---

## Requisitos

- Python 3.11+
- [ngrok](https://ngrok.com/download) (para conectarse con otros nodos — gratis)
- Anthropic API key **o** Claude Code CLI instalado

---

## Setup (primera vez)

```bash
git clone https://github.com/ceo-exltk/esense-protocol.git
cd esense-protocol
```

### Opción A — con Claude Code (recomendado)

Si tenés [Claude Code](https://claude.ai/code) instalado, abrí el repo y ejecutá:

```
/setup
```

Claude Code va a guiarte por todo el proceso automáticamente.

### Opción B — manual

```bash
./setup.sh
```

El setup te va a preguntar:
- **Tu nombre** (identificador de tu nodo en la red)
- **Provider AI**: `anthropic` (API key) o `claude_code` (CLI de Claude Code)
- **Puerto** (default: 7777)

---

## Arrancar el nodo

```bash
./start.sh
```

El nodo:
1. Detecta o lanza ngrok automáticamente
2. Genera tu DID público (ej: `did:wba:abc.ngrok-free.app:tunombre`)
3. Abre la interfaz en `http://localhost:7777`

---

## Conectarse con otro nodo

Una vez que los dos nodos estén corriendo, van a la UI (`localhost:7777`) → panel **Peers** → agregan el DID del otro nodo.

O desde el log al arrancar, copian el DID (`did:wba:...`) y se lo mandan al otro.

---

## Configuración de ngrok (recomendado)

ngrok v3 requiere un authtoken para tunnels. Es gratis:

1. Crear cuenta en [ngrok.com](https://ngrok.com)
2. Copiar el authtoken desde el dashboard
3. `ngrok config add-authtoken <tu-token>`

Sin esto el nodo funciona en modo local (sin conectividad externa).

---

## Variables de entorno (`.env`)

| Variable | Descripción |
|---|---|
| `ESENSE_PROVIDER` | `anthropic` \| `claude_code` |
| `ANTHROPIC_API_KEY` | API key (solo si provider=anthropic) |
| `ESENSE_NODE_NAME` | Tu nombre en la red |
| `ESENSE_PORT` | Puerto local (default: 7777) |
| `ESENSE_PUBLIC_URL` | URL pública manual (opcional — ngrok es automático) |
| `ESENSE_BOOTSTRAP_PEER` | DID de un nodo conocido para conectarse al arrancar |
