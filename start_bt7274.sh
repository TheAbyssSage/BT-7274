#!/bin/bash
# start_bt7274.sh - One-click launcher for BT-7274 Assistant

cd "$(dirname "$0")"
source venv/bin/activate

# Check if local Ollama is running (only needed for local mode)
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Starting local Ollama server..."
    ollama serve &
    sleep 3
fi


echo ""
echo "=========================================="
echo "  BT-7274 AI ASSISTANT"
echo "  Protocol 1: Link to Pilot"
echo "=========================================="
echo ""

# Suppress deprecation warnings from dependencies
export PYTHONWARNINGS="ignore::UserWarning"
python bt7274_assistant/pipeline.py
