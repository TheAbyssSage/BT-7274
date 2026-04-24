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
echo "Enhanced with TTS optimizations:"
echo "• Response caching for faster repeats"
echo "• Expanded standby clips library"
echo "• Improved text processing"
echo "• Memory management enhancements"
echo ""
echo "Say 'clear tts cache' or 'clear cache' to reset the TTS cache."
echo ""

# Performance Mode Selection
echo ""
echo "Select TTS Performance Mode:"
echo "  [1] Standard Mode - Full response synthesized, then played"
echo "      Best for: Short responses, maximum voice quality"
echo ""
echo "  [2] Performance Mode (STREAMING) - Sentence-level streaming"
echo "      Best for: Long responses, minimal latency"
echo "      ⚡ First audio plays in ~2-4 seconds"
echo "      ⚡ BT-7274's voice maintained throughout"
echo ""

# Default to standard mode if no input
PERFORMANCE_ARG=""
read -t 10 -p "Select mode [1-2] (default: 1): " choice || choice="1"

case "$choice" in
    2)
        echo "  → Selected: Performance Mode (Streaming)"
        PERFORMANCE_ARG="--performance-mode performance"
        ;;
    *)
        echo "  → Selected: Standard Mode"
        PERFORMANCE_ARG="--performance-mode standard"
        ;;
esac

echo ""

# Suppress deprecation warnings from dependencies
export PYTHONWARNINGS="ignore::UserWarning"
python bt7274_assistant/pipeline.py $PERFORMANCE_ARG
