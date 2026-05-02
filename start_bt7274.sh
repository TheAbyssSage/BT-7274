#!/bin/bash
# start_bt7274.sh - One-click launcher for BT-7274 Assistant

cd "$(dirname "$0")"
source venv/bin/activate

# Check if local Ollama is running (only needed for local mode)
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "  [SYS] Starting local Ollama server..."
    ollama serve &
    sleep 3
fi

# Input Mode Selection
echo ""
echo "  Select Input Mode:"
echo "    [1] Voice Mode       — Microphone + wake word"
echo "    [2] Console Chat     — Text input (like Ollama)"

MODE_ARG=""
while true; do
    read -r -p "  > Mode [1-2]: " mode_choice
    case "$mode_choice" in
        1) MODE_ARG="";      echo "  [SELECT] Voice Mode"; break ;;
        2) MODE_ARG="--console-chat-mode"; echo "  [SELECT] Console Chat"; break ;;
        *) echo "  Invalid choice. Enter 1 or 2." ;;
    esac
done

# Performance Mode Selection
echo ""
echo "  Select TTS Mode:"
echo "    [1] Standard    — Full synthesis, then play"
echo "    [2] Streaming   — Sentence-level parallel playback"

PERFORMANCE_ARG=""
while true; do
    read -r -p "  > TTS [1-2]: " choice
    case "$choice" in
        1) PERFORMANCE_ARG="--performance-mode standard"; echo "  [SELECT] Standard"; break ;;
        2) PERFORMANCE_ARG="--performance-mode performance"; echo "  [SELECT] Streaming"; break ;;
        *) echo "  Invalid choice. Enter 1 or 2." ;;
    esac
done

echo ""

# Suppress deprecation warnings from dependencies
export PYTHONWARNINGS="ignore::UserWarning"
python bt7274_assistant/pipeline.py $MODE_ARG $PERFORMANCE_ARG
