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
from location import LocationProvider
from utils import play_audio, PersistentAudioRecorder, beep


class BT7274Assistant:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = str(Path(__file__).parent / "config.yaml")
        self.config = self.load_config(config_path)
        self.stt: Optional[WhisperSTT] = None
        self.llm: Optional[OllamaClient] = None
        self.tts: Optional[XTTSClient] = None
        self.actions: Optional[ActionHandler] = None
        self.location: Optional[LocationProvider] = None
        self.recorder: Optional[PersistentAudioRecorder] = None
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

        print("[5/5] Initializing Location Services...")
        self.location = LocationProvider()
        if self.location.update():
            print(f"    📍 Location: {self.location.location_str}")
        else:
            print("    ⚠ Location unavailable.")

        print("[6/6] Opening persistent audio stream...")
        self.recorder = PersistentAudioRecorder(self.config["stt"])
        self.recorder.start()
        print("    ✓ Microphone stream active.")

        print("\n✓ All systems online.")
        print("  Say 'Hey BT' or press Enter to speak.\n")

    def _is_weather_query(self, text: str) -> bool:
        """Detect if the user is asking for weather."""
        return any(kw in text.lower() for kw in ["weather", "temperature", "forecast"])

    def _is_search_query(self, text: str) -> bool:
        """Detect if the user is asking for real-time info that needs a web search."""
        search_keywords = [
            "who won", "who is", "who was",
            "what is", "what are", "what's",
            "when is", "when was", "when are",
            "where is", "where are", "where can",
            "news", "latest", "current", "today",
            "search", "look up", "find", "tell me about"
        ]
        lower = text.lower()
        return any(kw in lower for kw in search_keywords)

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

        # Helper: speak a standby phrase immediately
        def speak_standby():
            phrases = self.config["pipeline"].get("standby_phrases", ["Copy that, Pilot. Stand by."])
            import random
            phrase = random.choice(phrases)
            print(f"  ⏳ {phrase}")
            wav = self.tts.speak(phrase)
            if wav:
                play_audio(wav)

        # 2. Detect weather query and fetch from Open-Meteo API
        response = None
        if self._is_weather_query(text):
            speak_standby()
            print("  🌤 Fetching local data...")
            weather_result = self.actions.execute("get_weather")
            if weather_result and not weather_result.startswith("Weather data unavailable"):
                print(f"  🌤 {weather_result}")
                print("  [LLM] Summarizing for Pilot...")
                summary_prompt = (
                    f"Pilot asked: {text}\n\n"
                    f"Weather data: {weather_result}\n\n"
                    f"Respond in character as BT-7274 with exactly ONE short sentence. "
                    f"Only the sentence. No quotes, no markdown, no extra text."
                )
                response = self.llm.chat(summary_prompt)
            else:
                response = "Pilot, atmospheric sensors are offline."

        # 3. Detect search intent and perform search BEFORE LLM
        if response is None and self._is_search_query(text):
            speak_standby()
            print("  🔍 Looking up...")
            # Enrich query with location context
            enriched_query = self.location.enrich_query(text) if self.location else text
            if enriched_query != text:
                print(f"    📍 Localized query: {enriched_query}")
            search_result = self.actions.execute("search_web", query=enriched_query)
            if search_result and not search_result.startswith("Action") and not search_result.startswith("Search failed"):
                print(f"  🔍 Results: {search_result[:100]}...")
                print("  [LLM] Summarizing for Pilot...")
                summary_prompt = (
                    f"Pilot asked: {text}\n\n"
                    f"Search results: {search_result}\n\n"
                    f"Respond in character as BT-7274 with exactly ONE short sentence. "
                    f"Only the sentence. No quotes, no markdown, no extra text."
                )
                response = self.llm.chat(summary_prompt)
            else:
                response = "Pilot, my sensors cannot reach the data network at this time."

        # 4. Normal LLM Processing (if not a search or weather query)
        if response is None:
            print("  [LLM] Thinking...")
            response = self.llm.chat(text)

        # Strip markdown, JSON, and instruction blocks before TTS
        import re
        clean_response = response
        # Remove markdown headers, code blocks, horizontal rules
        clean_response = re.sub(r'#{1,6}\s+.*', '', clean_response)
        clean_response = re.sub(r'```.*?```', '', clean_response, flags=re.DOTALL)
        clean_response = re.sub(r'---+', '', clean_response)
        clean_response = re.sub(r'\*\*.*?\*\*', '', clean_response)
        clean_response = re.sub(r'\{[^{}]*"action"[^{}]*\}', '', clean_response)
        clean_response = clean_response.strip()
        # Collapse multiple blank lines
        clean_response = '\n'.join(line for line in clean_response.splitlines() if line.strip())
        if not clean_response:
            clean_response = "Processing complete, Pilot."

        print(f"  🤖 BT-7274: \"{clean_response}\"")

        # 4. Text-to-Speech
        print("  [TTS] Synthesizing voice...")
        output_wav = self.tts.speak(clean_response)
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
                audio_path = self.recorder.record() if self.recorder else record_until_silence(self.config["stt"])

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
        finally:
            if self.recorder:
                print("  🎙 Closing microphone stream...")
                self.recorder.stop()
            self.running = False


def main():
    assistant = BT7274Assistant()
    assistant.run()


if __name__ == "__main__":
    main()
