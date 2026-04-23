# BT-7274 Local AI Assistant

A fully local AI assistant based on BT-7274 from Titanfall 2, designed to run on an Apple M1 MacBook Air with 16 GB RAM.

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Microphone  │────▶│ Whisper STT  │────▶│   Ollama    │────▶│  TTS Engine │────▶│   Speaker   │
│   Input     │     │  (local)     │     │   (LLM)     │     │(BT-7274 Voice)│    │   Output    │
└─────────────┘     └──────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                │
                                                ▼
                                         ┌─────────────┐
                                         │   Action    │
                                         │   Handler   │
                                         │(scripts/apps)│
                                         └─────────────┘
```

## Components

| Component | Tool / Model | Purpose | Hardware Fit |
|-----------|--------------|---------|--------------|
| Speech-to-Text | OpenAI Whisper (local) | Convert voice commands to text | ✅ Already installed, runs well on M1 |
| LLM / Conversation | Ollama + Phi-3 / Llama 3.1 | Intent recognition, conversation, personality | ✅ 8B models run smoothly on 16 GB M1 |
| Text-to-Speech | Coqui TTS (XTTS v2) | BT-7274 voice cloning & synthesis | ✅ ~4-6 GB RAM, CPU inference feasible |
| Action Handler | Python + AppleScript / shell | Execute tasks, control apps, run scripts | ✅ Native macOS integration |

## Folder Structure

```
BT-7274/
├── bt-7274.Modelfile          # Ollama model definition (BT-7274 personality)
├── BT-7274.Voicepack/         # Your extracted audio dataset
│   ├── metadata.csv           # Transcriptions for each audio file
│   ├── wav/                   # Processed WAV files (16 kHz, mono)
│   └── raw/                   # Original MP3 files
├── bt7274_assistant/          # Main application code
│   ├── config.yaml            # Configuration
│   ├── pipeline.py            # Main voice loop
│   ├── stt.py                 # Whisper STT wrapper
│   ├── tts.py                 # TTS engine (XTTS v2)
│   ├── llm.py                 # Ollama LLM client
│   ├── actions.py             # Task execution handler
│   └── utils.py               # Audio helpers
├── scripts/                   # Setup & utility scripts
│   ├── prepare_dataset.py     # Dataset cleaning & splitting
│   ├── train_voice.py         # XTTS v2 voice cloning setup
│   ├── test_tts.py            # Quick TTS test
│   └── install_deps.sh        # Dependency installer
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

---

## Step 1: Install Dependencies

### 1.1 System Prerequisites

Ensure you have:
- **macOS 12+** (Monterey or newer)
- **Homebrew** installed
- **Python 3.10+**
- **Whisper** already installed (as you mentioned)

### 1.2 Install Ollama

```bash
# Install Ollama for local LLM inference
curl -fsSL https://ollama.com/install.sh | sh

# Pull a recommended model (Phi-3 Medium or Llama 3.1 8B)
ollama pull phi3:medium
# OR
ollama pull llama3.1:8b
```

**Model Recommendations for M1 16GB:**

| Model | Size | Quality | Speed | Best For |
|-------|------|---------|-------|----------|
| `phi3:mini` | 3.8B | Good | Very Fast | Quick responses, low RAM |
| `phi3:medium` | 14B | Excellent | Medium | Best balance (recommended) |
| `llama3.1:8b` | 8B | Very Good | Fast | Strong reasoning |
| `mistral:7b` | 7B | Very Good | Fast | Good instruction following |

> **Note:** `phi3:medium` uses ~8-10 GB RAM. With 16 GB total, close other heavy apps while running.

### 1.3 Install Python Dependencies

```bash
# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install -r requirements.txt
```

### 1.4 Install Coqui TTS (XTTS v2)

```bash
# Install Coqui TTS for voice cloning
pip install TTS

# On Apple Silicon, you may need to install PyTorch with MPS support first:
pip install torch torchvision torchaudio

# Verify TTS installation
tts --list_models | grep xtts
```

> **M1 Optimization:** Coqui TTS will use CPU by default on M1. For MPS (Metal) acceleration, ensure you have `torch>=2.0` with MPS backend. However, XTTS v2 currently runs best on CPU for Apple Silicon.

---

## Step 2: Prepare the BT-7274 Voice Dataset

Your `metadata.csv` already has transcriptions — great! But we need to clean and standardize the audio for training.

### 2.1 Dataset Requirements for XTTS v2

- **Format:** WAV, mono, 16-bit, **22050 Hz** (XTTS v2 native sample rate)
- **Length:** Individual clips of 2–10 seconds work best
- **Content:** Clean speech without music, SFX, or overlapping dialogue
- **Quantity:** You have ~50 files. For zero-shot cloning, 1–2 minutes of clean audio is sufficient. For best results, 5–10 minutes is ideal.

### 2.2 Run Dataset Preparation

```bash
source venv/bin/activate
python scripts/prepare_dataset.py
```

This script will:
1. Convert all MP3/WAV files to 22050 Hz mono WAV
2. Split long files (like the compilation) into shorter clips using voice activity detection (VAD)
3. Normalize audio levels
4. Create a `dataset/` folder with clean, training-ready audio

### 2.3 Manual Cleanup (Recommended)

After running the script, listen to the clips in `dataset/wavs/` and remove any that:
- Contain music, gunfire, or heavy SFX
- Have overlapping dialogue
- Are too quiet or distorted

The cleaner the dataset, the better the cloned voice.

---

## Step 3: Voice Cloning with XTTS v2

XTTS v2 is a **zero-shot voice cloning** model. You do not need to train it from scratch. Instead, you provide a reference speaker audio file, and the model clones that voice for any text.

### 3.1 How XTTS v2 Works

```
Text Input ──▶ XTTS v2 Model ──▶ Speaker Encoder ──▶ BT-7274 Voice Output
                    │                    │
                    └────────────────────┘
                         (your audio samples)
```

The model was pre-trained on thousands of speakers. The "speaker encoder" extracts voice characteristics from your reference audio and applies them to the generated speech.

### 3.2 Create a Reference Speaker File

For the best results, concatenate your best 5–10 clean clips into one reference file:

```bash
# Use the preparation script to create a reference speaker file
python scripts/prepare_dataset.py --create-reference
```

This creates `dataset/reference_speaker.wav` (~30–60 seconds of clean BT-7274 speech).

### 3.3 Test Voice Cloning

```bash
# Generate a test phrase in BT-7274's voice
python scripts/test_tts.py --text "Pilot, I am standing by."
```

This will:
1. Load XTTS v2
2. Encode your reference speaker
3. Generate `test_output.wav`

Listen to it. If it sounds good, you're ready!

### 3.4 Fine-Tuning (Optional, Advanced)

If zero-shot cloning isn't accurate enough, you can fine-tune XTTS v2 on your dataset. **Warning:** This requires significant time and ~8 GB VRAM (not feasible on M1 integrated GPU). On CPU, it would take days.

**Alternative:** Use the **GPT-SoVITS** or **F5-TTS** models, which fine-tune faster on CPU. However, XTTS v2 zero-shot is usually sufficient with a good reference.

---

## Step 4: Set Up Ollama with BT-7274 Personality

You already have a `Modelfile`. Let's build and test it.

### 4.1 Build the Model

```bash
cd /path/to/BT-7274
ollama create bt7274 -f bt-7274.Modelfile
```

### 4.2 Test the Model

```bash
ollama run bt7274
```

Try prompts like:
- "Status report, BT."
- "We're under attack!"
- "Tell me about Protocol 3."

### 4.3 Enhanced Modelfile (Recommended)

For better intent recognition and action handling, use an enhanced system prompt. See `bt7274_assistant/config.yaml` for the full prompt template.

---

## Step 5: The Integration Pipeline

The main application ties everything together.

### 5.1 Configuration

Edit `bt7274_assistant/config.yaml` to set your preferences:

```yaml
stt:
  model: base.en          # Whisper model size (tiny/base/small/medium)
  language: en
  device: cpu             # or 'mps' if available

llm:
  # Local Ollama settings
  local:
    model: bt7274         # Your Ollama model
    url: http://localhost:11434
    temperature: 0.7
    max_tokens: 200
  # Cloud Ollama settings
  cloud:
    model: gpt-oss:120b-cloud
    url: http://localhost:11434
    temperature: 0.7
    max_tokens: 300       # Larger context for cloud models
  # Current mode (local or cloud)
  mode: local
  system_prompt: |
    You are BT-7274, a Vanguard-class Titan from the game Titanfall 2.
    ...

tts:
  model: tts_models/multilingual/multi-dataset/xtts_v2
  reference_wav: dataset/reference_speaker.wav
  language: en
  speed: 1.0

actions:
  enabled: true
  allowed_commands:
    - say
    - open
    - run_script
    - set_volume
    - tell_time
```

### 5.2 Run the Pipeline

```bash
source venv/bin/activate

# Run the assistant (will prompt for model selection)
python bt7274_assistant/pipeline.py
```

The pipeline runs in a loop:
1. **Listen:** Records audio from your microphone until silence is detected
2. **Transcribe:** Sends audio to Whisper → text
3. **Think:** Sends text to the AI (Ollama) → response text + intent
4. **Act:** If the intent is an action (e.g., "open Safari"), executes it
5. **Speak:** Sends response text to XTTS v2 → BT-7274 voice audio → plays through speakers

### 5.3 Startup Sequence

When you start the assistant, it will:
1. **Initialize Speech-to-Text:** Load and activate the Whisper model
2. **Select LLM:** Choose between Local or Cloud Ollama by entering 1 or 2
3. **Initialize LLM:** Connect to the selected Ollama instance
4. **Initialize Text-to-Speech:** Load the XTTS v2 voice model
5. **Initialize Action Handler:** Set up command execution
6. **Initialize Location Services:** Detect your location
7. **Open Audio Stream:** Start listening for voice commands

### 5.4 Using the Startup Script

For convenience, you can use the provided startup script:

```bash
# Start the assistant
./start_bt7274.sh
```

### 5.3 Wake Word (Optional)

To avoid processing all ambient audio, add a wake word like "Hey BT" or "BT-7274":

```yaml
wake_word: "hey bt"
```

The pipeline will only process commands after detecting the wake word.

### 5.4 Cloud Model Selection

You can choose between different models on the same Ollama instance:

1. **Local Model**: A lightweight model that runs efficiently on your local machine
2. **Cloud Model**: A more powerful model (like gpt-oss:120b-cloud) that provides better responses and larger context windows

Configure both models in `config.yaml`:
```yaml
llm:
  # Local Ollama settings
  local:
    model: bt7274
    url: http://localhost:11434
    temperature: 0.7
    max_tokens: 200
  # Cloud Ollama settings (same server, different model)
  cloud:
    model: gpt-oss:120b-cloud
    url: http://localhost:11434
    temperature: 0.7
    max_tokens: 300       # Larger context for cloud models
```

During startup, you can use the arrow keys to select which model to use:
- ↑/↓ to navigate between Local Ollama and Cloud Ollama
- Enter to confirm your selection

Benefits of the cloud model:
- More powerful reasoning capabilities
- Larger context windows for better understanding
- Higher quality responses
- Better instruction following

---

## Step 6: Action Handler (Task Execution)

BT-7274 can execute tasks. The action handler parses intents from the LLM response and runs them.

### 6.1 Supported Actions

| Command | Example Voice Command | What It Does |
|---------|----------------------|--------------|
| `say` | "Say 'Protocol 3'" | Speaks arbitrary text |
| `open` | "Open Safari" | Opens macOS applications |
| `run_script` | "Run the lights script" | Executes shell scripts |
| `set_volume` | "Set volume to 50%" | Adjusts system volume |
| `tell_time` | "What time is it?" | Speaks current time |
| `web_search` | "Search for Titanfall" | Opens browser with query |

### 6.2 Adding Custom Actions

Edit `bt7274_assistant/actions.py` to add your own. Example:

```python
@register_action("trigger_automation")
def trigger_automation(name: str):
    """Trigger a HomeKit or Shortcuts automation."""
    os.system(f'shortcuts run "{name}"')
    return f"Automation '{name}' triggered."
```

Then say: "BT, trigger automation Good Morning"

---

## Step 7: Hardware Optimizations for M1 MacBook Air

### 7.1 RAM Management

With 16 GB RAM, running Whisper + Ollama + XTTS v2 simultaneously is tight. Strategies:

1. **Use smaller Whisper models:** `base.en` instead of `small.en` (saves ~1 GB)
2. **Use quantized LLMs:** Ollama automatically uses 4-bit quantization
3. **Unload models when idle:** The pipeline can unload TTS/LLM after a timeout
4. **Close other apps:** Quit browsers, IDEs, etc. while cosplaying

### 7.2 CPU vs. MPS (Metal)

| Component | CPU | MPS (Metal GPU) | Recommendation |
|-----------|-----|-----------------|----------------|
| Whisper | ✅ Stable | ✅ Faster (if supported) | Try MPS first |
| Ollama | ✅ Stable | ✅ Faster | Ollama auto-detects |
| XTTS v2 | ✅ Works | ❌ Not well supported | Use CPU |

To enable MPS for Whisper, set `device: mps` in `config.yaml`.

### 7.3 Inference Speed Expectations

| Step | Model | Expected Latency (M1 Air) |
|------|-------|---------------------------|
| STT (Whisper base) | ~1–3 sec for 5 sec audio | Real-time capable |
| LLM (Phi-3 14B) | ~2–5 sec for 50 tokens | Good |
| TTS (XTTS v2) | ~3–8 sec for 10 words | Acceptable |
| **Total round-trip** | | **~6–16 seconds** |

For faster TTS, consider **Piper TTS** as a fallback for short responses.

### 7.4 Thermal Throttling

The M1 MacBook Air has no fan. During extended use:
- The CPU may throttle after 10–15 minutes of heavy load
- Take breaks between sessions
- Use a laptop stand for airflow

---

## Step 8: Running at Cosplay Events

### 8.1 Portable Setup

1. **Bluetooth headset with mic:** Hands-free voice commands
2. **Portable speaker:** For BT-7274's voice (wearable or nearby)
3. **Battery pack:** Extend MacBook Air battery life
4. **Offline mode:** Everything runs locally — no Wi-Fi needed after setup

### 8.2 Quick-Start Script

Create a one-click launcher:

```bash
#!/bin/bash
# start_bt7274.sh
cd /path/to/BT-7274
source venv/bin/activate
ollama serve &
sleep 2
python bt7274_assistant/pipeline.py
```

Make it executable: `chmod +x start_bt7274.sh`

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Out of memory" error | Use smaller models, close other apps, or enable model unloading |
| TTS sounds robotic | Use a longer, cleaner reference speaker file (30+ sec) |
| Whisper misses words | Use `small.en` instead of `base.en`, or speak closer to the mic |
| Ollama slow responses | Switch to `phi3:mini` or `llama3.1:8b` |
| Audio playback delayed | Reduce TTS chunk size or use Piper for short phrases |
| Microphone not detected | Check macOS Privacy & Security → Microphone permissions |

---

## Legal & Ethical Note

This project is for **personal cosplay use only**. BT-7274 and Titanfall 2 are intellectual property of Respawn Entertainment / Electronic Arts. Do not distribute the voice model or generated audio commercially. The voice cloning is intended as a fan tribute and should remain non-commercial.

---

## Next Steps

1. ✅ Install dependencies (Step 1)
2. ✅ Prepare your dataset (Step 2)
3. ✅ Test voice cloning (Step 3)
4. ✅ Set up Ollama personality (Step 4)
5. ✅ Run the full pipeline (Step 5)
6. 🎉 Suit up, Pilot!

**Good luck with your cosplay, Pilot. Protocol 3: Protect the cosplayer.**
