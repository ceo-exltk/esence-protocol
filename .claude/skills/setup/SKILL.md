---
name: setup
description: Instala y configura el nodo Esense. Usar cuando el usuario acaba de clonar el repo o quiere hacer setup inicial.
allowed-tools: Bash, Read, Write, Edit
---

Sos el asistente de instalación del nodo Esense. Ejecutá los siguientes pasos en orden, verificando cada uno antes de continuar.

## Paso 1 — Verificar Python

```bash
python3 --version
```

Si la versión es menor a 3.11, avisar al usuario y detener.

## Paso 2 — Verificar ngrok

```bash
which ngrok && ngrok version || echo "ngrok no encontrado"
```

Si ngrok no está instalado, indicar:
> "Instalá ngrok desde https://ngrok.com/download — es gratis y necesario para conectarte con otros nodos."
> "Una vez instalado, ejecutá: ngrok config add-authtoken <tu-token>"
> "(podés continuar sin ngrok, el nodo va a funcionar en modo local)"

## Paso 3 — Instalar dependencias Python

```bash
pip install -r requirements.txt --quiet && echo "OK"
```

## Paso 4 — Verificar .env

```bash
ls .env 2>/dev/null && echo "existe" || echo "no existe"
```

Si `.env` no existe:
```bash
cp .env.example .env
```

Luego verificar si el nombre del nodo ya está configurado:
```bash
grep ESENSE_NODE_NAME .env
```

Si el valor es `yourname` o está vacío, pedirle al usuario su nombre y actualizar el .env:
```bash
sed -i '' 's/ESENSE_NODE_NAME=yourname/ESENSE_NODE_NAME=NOMBRE_AQUI/' .env
```

## Paso 5 — Verificar provider AI

Leer `.env` y verificar que:
- Si `ESENSE_PROVIDER=anthropic` → `ANTHROPIC_API_KEY` no está vacío
- Si `ESENSE_PROVIDER=claude_code` → verificar que `claude` CLI está instalado con `which claude`

Si falta la API key, pedirla al usuario y agregarla al `.env`.

## Paso 6 — Generar identidad

```bash
ls essence-store/identity.json 2>/dev/null && echo "existe" || echo "no existe"
```

Si no existe, correr el setup interactivo:
```bash
python3 -m esense.setup
```

## Paso 7 — Test rápido

```bash
python3 -m pytest tests/ -q --tb=short 2>&1 | tail -3
```

## Paso 8 — Resumen final

Leer `essence-store/identity.json` y mostrar:
- DID del nodo
- Puerto configurado
- Provider AI activo
- Estado de ngrok

Terminar con:
> "✓ Setup completo. Ejecutá **./start.sh** para arrancar tu nodo Esense."
> "Una vez arrancado, compartí tu DID con el otro nodo para conectarse."
