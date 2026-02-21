#!/bin/bash
# Esence Node — Start Script

set -e

echo "⚡ Starting Esence node..."
echo "   Interface → http://localhost:7777"
echo ""

if [ -z "$ESENCE_PUBLIC_URL" ]; then
  ESENCE_PORT=${ESENCE_PORT:-7777}
  echo "  Tip: para conectar con otros nodos:"
  echo "       ngrok http $ESENCE_PORT  →  ESENCE_PUBLIC_URL=https://... en .env"
  echo ""
fi

# Open browser after short delay
(sleep 2 && python3 -c "import webbrowser; webbrowser.open('http://localhost:7777')") &

# Start node
python3 -m esence.core.node
