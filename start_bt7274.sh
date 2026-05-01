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
echo "======================================"
echo "                                        "
echo "      BT-7274 AI ASSISTANT            "
echo "      Protocol 1: Link to Pilot        "
echo "                                        "
echo "======================================"
echo ""
echo "  Enhanced with TTS optimizations:"
echo "    - Response caching for faster repeats"
echo "    - Expanded standby clips library"
echo "    - Improved text processing"
echo "    - Memory management enhancements"
echo ""
echo "  Say 'clear tts cache' or 'clear cache' to reset the TTS cache."
echo ""

# Input Mode Selection — waits indefinitely for a choice
echo "──────────────────────────────────────────"
echo "  Select Input Mode:"
echo ""
echo "    [1] Voice Mode (Microphone)"
echo "        Full voice assistant with wake word detection"
echo "        Best for: Hands-free operation, immersive experience"
echo ""
echo "    [2] Console Chat Mode"
echo "        Text-based terminal chat like local Ollama"
echo "        Best for: Testing, debugging, quiet environments"
echo "        Looks like:  > BT, where are we?"
echo ""
echo "──────────────────────────────────────────"

MODE_ARG=""
while true; do
    read -r -p "  > Select mode [1-2]: " mode_choice
    case "$mode_choice" in
        1)
            echo "  [SELECT] Voice Mode (Microphone)"
            MODE_ARG=""
            break
            ;;
        2)
            echo "  [SELECT] Console Chat Mode"
            MODE_ARG="--console-chat-mode"
            break
            ;;
        *)
            echo "  Invalid choice. Please enter 1 or 2."
            ;;
    esac
done

echo ""

# Performance Mode Selection — waits indefinitely for a choice
echo "──────────────────────────────────────────"
echo "  Select TTS Performance Mode:"
echo ""
echo "    [1] Standard Mode"
echo "        Full response synthesized, then played"
echo "        Best for: Short responses, maximum voice quality"
echo ""
echo "    [2] Performance Mode (STREAMING)"
echo "        Sentence-level streaming with parallel synthesis"
echo "        Best for: Long responses, minimal latency"
echo "        First audio plays in ~2-4 seconds"
echo "        BT-7274's voice maintained throughout"
echo ""
echo "──────────────────────────────────────────"

PERFORMANCE_ARG=""
while true; do
    read -r -p "  > Select mode [1-2]: " choice
    case "$choice" in
        1)
            echo "  [SELECT] Standard Mode"
            PERFORMANCE_ARG="--performance-mode standard"
            break
            ;;
        2)
            echo "  [SELECT] Performance Mode (Streaming)"
            PERFORMANCE_ARG="--performance-mode performance"
            break
            ;;
        *)
            echo "  Invalid choice. Please enter 1 or 2."
            ;;
    esac
done

echo ""

# Suppress deprecation warnings from dependencies
export PYTHONWARNINGS="ignore::UserWarning"
python bt7274_assistant/pipeline.py $MODE_ARG $PERFORMANCE_ARG
