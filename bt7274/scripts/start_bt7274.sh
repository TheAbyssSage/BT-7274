#!/bin/bash
# start_bt7274.sh - One-click launcher for BT-7274 Assistant
# Delegates to the unified `bt7274` CLI (`bt7274 bt-link`).

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_DIR"

if [[ ! -d "venv" ]]; then
    echo "  [ERR] Virtual environment not found at $PROJECT_DIR/venv"
    echo "        Run: python3 -m venv venv && source venv/bin/activate && pip install -e ."
    exit 1
fi

source venv/bin/activate

# Verify the package is installed in editable mode.
if ! command -v bt7274 >/dev/null 2>&1; then
    echo "  [ERR] bt7274 command not found. Installing package in editable mode..."
    pip install -e "$PROJECT_DIR"
fi

# Launch the full Protocol 1 sequence (Ollama check + mode selection + assistant)
bt7274 bt-link
