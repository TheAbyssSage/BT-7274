#!/usr/bin/env python3
"""
BT-7274 Voice Assistant - Main Pipeline
Microphone → Whisper STT → Ollama LLM → XTTS v2 → Speaker
"""

import os
import sys
import json
import time
import tempfile
import threading
from pathlib import Path
from typing import Optional

import yaml
import numpy as np
import sounddevice as sd
import soundfile as sf

# Import our modules
sys.path.insert(0, str(Path(__file__).parent))
from stt import WhisperSTT
from llm import OllamaClient
from tts import XTTSClient
from actions import ActionHandler
from utils import play_audio, record_until_silence, beep


class BT7274Assistant:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = str(Path(__file__).parent / "config.yaml")
        self.config = self.load_config(config_path)
        self.stt: Optional[WhisperSTT] = None
        self.llm: Optional[OllamaClient] = None
        self.tts: Optional[XTTSClient] = None
        self.actions: Optional[ActionHandler] = None
        self.running = False
        self.last_activity = time.time()

    def load_config(self, path: str) -> dict:
        with open(path, 'r') as f:
            return yaml.safe_load(f)

    def initialize(self):
        """Initialize all components."""
        print("=" * 50)
        print("  BT-7274 LOCAL AI ASSISTANT")
        print("  Protocol 1: Link to Pilot")
        print("=" * 50)

        print("\n[1/4] Initializing Speech-to-Text...")
        self.stt = WhisperSTT(self.config["stt"])

        print("[2/4] Initializing LLM (Ollama)...")
        self.llm = OllamaClient(self.config["llm"])

        print("[3/4] Initializing Text-to-Speech...")
        self.tts = XTTSClient(self.config["tts"])

        print("[4/4] Initializing Action Handler...")
        self.actions = ActionHandler(self.config["actions"])

        print("\n✓ All systems online.")
        print("  Say 'Hey BT' or press Enter to speak.\n")

    def process_command(self, audio_path: str) -> bool:
        """Process a single voice command."""
        # 1. Speech-to-Text
        print("\n  [STT] Transcribing...")
        text = self.stt.transcribe(audio_path)
        if not text or not text.strip():
            print("  ✗ No speech detected.")
            return False

        print(f"  🎤 Pilot: \"{text}\"")

        # Check wake words
        wake_words = self.config["pipeline"].get("wake_words", [])
        if wake_words and not any(ww.lower() in text.lower() for ww in wake_words):
            print(f"  ⏭ Wake word not detected. Ignoring.")
            return False

        # 2. LLM Processing
        print("  [LLM] Thinking...")
        response = self.llm.chat(text)
        print(f"  🤖 BT-7274: \"{response}\"")

        # 3. Action Handling
        action_result = None
        if self.config["actions"]["enabled"]:
            action_result = self.actions.parse_and_execute(response)
            if action_result:
                print(f"  ⚡ Action: {action_result}")

        # 4. Text-to-Speech
        print("  [TTS] Synthesizing voice...")
        output_wav = self.tts.speak(response)
        if output_wav:
            play_audio(output_wav)

        self.last_activity = time.time()
        return True

    def run(self):
        """Main voice interaction loop."""
        self.initialize()
        self.running = True

        try:
            while self.running:
                # Option 1: Voice-activated recording
                if self.config["pipeline"].get("play_beep"):
                    beep()

                print("\n  🎙 Listening... (speak now)")
                audio_path = record_until_silence(self.config["stt"])

                if audio_path:
                    self.process_command(audio_path)
                    # Clean up temp file
                    try:
                        os.remove(audio_path)
                    except:
                        pass

                # Idle timeout check
                idle_timeout = self.config["pipeline"].get("idle_timeout", 300)
                if time.time() - self.last_activity > idle_timeout:
                    print("\n  💤 Idle timeout. Unloading models to save RAM...")
                    # Optional: unload models here if memory is tight

        except KeyboardInterrupt:
            print("\n\n  👋 Goodbye, Pilot.")
            self.running = False


def main():
    assistant = BT7274Assistant()
    assistant.run()


if __name__ == "__main__":
    main()
