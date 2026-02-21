#!/bin/bash
# Esence Node — Setup Script
# Genera identidad, configura API key y donation %, inicializa essence store

set -e

echo ""
echo "  ███████╗███████╗███████╗███╗   ██╗ ██████╗███████╗"
echo "  ██╔════╝██╔════╝██╔════╝████╗  ██║██╔════╝██╔════╝"
echo "  █████╗  ███████╗█████╗  ██╔██╗ ██║██║     █████╗  "
echo "  ██╔══╝  ╚════██║██╔══╝  ██║╚██╗██║██║     ██╔══╝  "
echo "  ███████╗███████║███████╗██║ ╚████║╚██████╗███████╗"
echo "  ╚══════╝╚══════╝╚══════╝╚═╝  ╚═══╝ ╚═════╝╚══════╝"
echo ""
echo "  Protocol v0.2 — Genesis Node Setup"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required. Please install it first."
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt --quiet

# Run setup
echo "🔑 Generating node identity..."
python3 -m esence.setup

echo ""
echo "✅ Node setup complete."
echo "   Run ./start.sh to launch your Esence node."
echo ""
