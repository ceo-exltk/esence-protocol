#!/bin/bash
# Esence Node — Start Script

set -e

echo "⚡ Starting Esence node..."
echo "   Interface → http://localhost:7777"
echo ""

# Open browser after short delay
(sleep 2 && python3 -c "import webbrowser; webbrowser.open('http://localhost:7777')") &

# Start node
python3 -m esence.core.node
