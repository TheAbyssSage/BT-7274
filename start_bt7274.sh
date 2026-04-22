#!/bin/bash
# start_bt7274.sh - One-click launcher for BT-7274 Assistant

cd "$(dirname "$0")"
source venv/bin/activate

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Starting Ollama server..."
    ollama serve &
    sleep 3
fi

echo ""
echo "=========================================="
echo "  BT-7274 LOCAL AI ASSISTANT"
echo "  Protocol 1: Link to Pilot"
echo "=========================================="
echo ""

python bt7274_assistant/pipeline.py
