#!/bin/bash
# install_deps.sh - Install all dependencies for BT-7274 Assistant on macOS M1

set -e

echo "=========================================="
echo "  BT-7274 Assistant - Dependency Installer"
echo "=========================================="

# Check for Homebrew
if ! command -v brew &> /dev/null; then
    echo "❌ Homebrew not found. Please install it first:"
    echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
fi

echo ""
echo "[1/6] Installing system dependencies..."
brew install python@3.11 ffmpeg portaudio

echo ""
echo "[2/6] Setting up Python virtual environment..."
cd "$(dirname "$0")/.."
python3.11 -m venv venv
source venv/bin/activate

echo ""
echo "[3/6] Upgrading pip..."
pip install --upgrade pip wheel setuptools

echo ""
echo "[4/6] Installing PyTorch (M1 optimized)..."
pip install torch torchvision torchaudio

echo ""
echo "[5/6] Installing Python packages..."
pip install -r requirements.txt

echo ""
echo "[6/6] Installing Ollama..."
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "    Ollama already installed."
fi

echo ""
echo "Pulling recommended LLM model..."
ollama pull phi3:medium

echo ""
echo "=========================================="
echo "  ✅ Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Activate venv: source venv/bin/activate"
echo "  2. Prepare dataset: python bt7274_assistant/scripts/prepare_dataset.py"
echo "  3. Test TTS: python bt7274_assistant/scripts/test_tts.py"
echo "  4. Build Ollama model: ollama create bt7274 -f bt-7274.Modelfile"
echo "  5. Run assistant: python bt7274_assistant/pipeline.py"
echo ""
