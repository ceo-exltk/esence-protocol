#!/bin/bash
# Esense Node — Start Script

set -e

echo "⚡ Starting Esense node..."
echo "   Interface → http://localhost:7777"
echo ""

# Open browser after short delay
(sleep 2 && python3 -c "import webbrowser; webbrowser.open('http://localhost:7777')") &

# Start node
python3 -m esense.core.node
