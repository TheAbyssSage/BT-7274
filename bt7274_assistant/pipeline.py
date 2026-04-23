#!/usr/bin/env python3
"""
BT-7274 Voice Assistant - Main Pipeline
Microphone → Whisper STT → Ollama LLM → XTTS v2 → Speaker
"""

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

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
from llm import OllamaClient, CloudLLMClient
from tts import XTTSClient
from actions import ActionHandler
from location import LocationProvider
from utils import play_audio, PersistentAudioRecorder, beep


class BT7274Assistant:
    def __init__(self, config_path: str = None, ai_mode: str = "local"):
        if config_path is None:
            config_path = str(Path(__file__).parent / "config.yaml")
        self.config = self.load_config(config_path)
        self.ai_mode = ai_mode  # "local" or "cloud"
        self.stt: Optional[WhisperSTT] = None
        self.llm: Optional[OllamaClient] = None
        self.tts: Optional[XTTSClient] = None
        self.actions: Optional[ActionHandler] = None
        self.location: Optional[LocationProvider] = None
        self.recorder: Optional[PersistentAudioRecorder] = None
        self.standby_clips: dict[str, str] = {}  # phrase -> wav_path
        self.running = False
        self.last_activity = time.time()

    def load_config(self, path: str) -> dict:
        with open(path, 'r') as f:
            return yaml.safe_load(f)

    def initialize(self):
        """Initialize all components."""
        print("=" * 50)
        print("  BT-7274 AI ASSISTANT")
        print("  Protocol 1: Link to Pilot")
        print("=" * 50)

        print("\n[1/7] Initializing Speech-to-Text...")
        self.stt = WhisperSTT(self.config["stt"])
        # Preload Whisper model to avoid delays during first transcription
        _ = self.stt.model
        print("    ✓ Whisper model loaded and ready.")

        print("\n[2/7] Which LLM?")
        if self.ai_mode is None:
            # Simple and reliable model selection
            local_model = self.config["llm"]["local"]["model"]
            cloud_model = self.config["llm"]["cloud"]["model"]
            
            print(f"  [1] Local Ollama  ({local_model})")
            print(f"  [2] Cloud Ollama  ({cloud_model})")
            
            while True:
                try:
                    choice = input("\nSelect model [1-2]: ").strip()
                    if choice == "1":
                        self.ai_mode = "local"
                        print(f"  → Selected: Local Ollama ({local_model})")
                        break
                    elif choice == "2":
                        self.ai_mode = "cloud"
                        print(f"  → Selected: Cloud Ollama ({cloud_model})")
                        break
                    else:
                        print("  Invalid choice. Please enter 1 or 2.")
                except (EOFError, KeyboardInterrupt):
                    print("\n  Exiting...")
                    sys.exit(0)
        else:
            # Use the provided AI mode
            mode_name = "Local Ollama" if self.ai_mode == "local" else "Cloud Ollama"
            model_name = self.config["llm"][self.ai_mode]["model"]
            print(f"  → Using: {mode_name} ({model_name}) (preselected)")

        print(f"\n[3/7] Initializing LLM ({'Local' if self.ai_mode == 'local' else 'Cloud'} Ollama)...")
        # Use OllamaClient for both local and cloud since they use the same API
        # Merge system prompt from top-level llm config
        llm_config = self.config["llm"][self.ai_mode].copy()
        llm_config["system_prompt"] = self.config["llm"].get("system_prompt", "")
        self.llm = OllamaClient(llm_config)

        print("\n[4/7] Initializing Text-to-Speech...")
        self.tts = XTTSClient(self.config["tts"])
        # Preload TTS model at startup to avoid delays during first synthesis
        _ = self.tts.model  # Trigger model loading
        print("    ✓ TTS model loaded and ready.")

        print("    Loading pre-recorded standby clips...")
        self._load_standby_clips()

        print("\n[5/7] Initializing Action Handler...")
        self.actions = ActionHandler(self.config["actions"])

        print("\n[6/7] Initializing Location Services...")
        manual_loc = self.config.get("location", {}).get("manual")
        self.location = LocationProvider(manual_location=manual_loc)
        if self.location.update():
            print(f"    📍 Location: {self.location.location_str}")
        else:
            print("    ⚠ Location unavailable.")

        print("\n[7/7] Opening persistent audio stream...")
        self.recorder = PersistentAudioRecorder(self.config["stt"])
        self.recorder.start()
        print("    ✓ Microphone stream active.")

        print("\n✓ All systems online.")
        print("  Say 'Hey BT' or press Enter to speak.\n")

    def _normalize_phrase(self, phrase: str) -> str:
        """Normalize a phrase for dictionary lookup."""
        import re
        phrase = phrase.lower().strip()
        phrase = re.sub(r'[^\w\s]', '', phrase)  # remove punctuation
        phrase = re.sub(r'\s+', ' ', phrase)     # collapse spaces
        return phrase

    def _load_standby_clips(self):
        """Load pre-recorded standby WAV files from standby/ folder."""
        standby_dir = Path(__file__).parent.parent / "standby"
        if not standby_dir.exists():
            print("    ⚠ No standby/ folder found. Will generate TTS on the fly.")
            return
        for wav_file in standby_dir.glob("*.wav"):
            phrase = wav_file.stem.replace("_", " ")
            key = self._normalize_phrase(phrase)
            self.standby_clips[key] = str(wav_file)
        print(f"    ✓ Loaded {len(self.standby_clips)} standby clips.")

    def _extract_location_from_query(self, text: str) -> Optional[str]:
        """Extract location from weather query like 'weather in Tucson, Arizona'."""
        import re
        lower = text.lower()
        # Match patterns like "weather in X", "weather for X", "temperature in X"
        # Exclude common time words that shouldn't be treated as locations
        time_words = {"today", "tomorrow", "yesterday", "now", "tonight"}
        patterns = [
            r'weather\s+(?:in|for|at|near)\s+(.+?)(?:\?|$)',
            r'temperature\s+(?:in|for|at|near)\s+(.+?)(?:\?|$)',
            r'forecast\s+(?:in|for|at|near)\s+(.+?)(?:\?|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, lower)
            if match:
                location = match.group(1).strip()
                # Don't treat time words as locations
                if location in time_words:
                    return None
                return location
        return None

    def _is_weather_query(self, text: str) -> bool:
        """Detect if the user is asking for weather."""
        return any(kw in text.lower() for kw in ["weather", "temperature", "forecast"])

    def _is_location_query(self, text: str) -> bool:
        """Detect if the user is asking for their location."""
        lower = text.lower()
        return any(kw in lower for kw in ["my location", "where am i", "where are we", "find my location", "what is my location"])

    def _is_time_query(self, text: str) -> bool:
        """Detect if the user is asking for the time/date."""
        lower = text.lower()
        time_keywords = ["what time", "what is the time", "current time", "what date", "what is the date", "today's date", "the date today", "what day", "what day is it"]
        return any(kw in lower for kw in time_keywords)

    def _is_search_query(self, text: str) -> bool:
        """Detect if the user is asking for real-time info that needs a web search."""
        search_keywords = [
            "who won", "who was",
            "news", "latest",
            "search", "look up", "tell me about"
        ]
        lower = text.lower()
        return any(kw in lower for kw in search_keywords)

    def _is_travel_query(self, text: str) -> bool:
        """Detect if the user is asking about travel or transportation."""
        travel_keywords = [
            "how to get", "how do i get", "travel to", "transport to", "go to", 
            "way to", "route to", "directions to", "getting to", "trip to",
            "visit", "journey to", "commute to", "drive to", "fly to", 
            "how do we get", "how to reach", "how can i get", "get to",
            "options to get to", "best way to", "fastest way to", "how do i reach"
        ]
        lower = text.lower()
        return any(kw in lower for kw in travel_keywords)

    def _mentions_destination(self, text: str) -> bool:
        """Detect if the user is mentioning getting to a specific destination."""
        # Common destinations that people ask about
        destinations = [
            "brussels", "belgium", "paris", "london", "berlin", "amsterdam",
            "madrid", "rome", "vienna", "prague", "budapest", "warsaw",
            "cologne", "hamburg", "munich", "frankfurt", "milan", "barcelona",
            "lisbon", "athens", "stockholm", "copenhagen", "oslo", "helsinki",
            "comic con", "expo", "conference", "event"
        ]
        lower = text.lower()
        return any(dest in lower for dest in destinations)

    def _is_requesting_travel_options(self, text: str) -> bool:
        """Detect if the user is specifically asking for travel options from their location."""
        # Check for combinations of travel-related words and destination mentions
        travel_indicators = ["how", "options", "ways", "methods", "best way", "fastest way"]
        location_indicators = ["from my location", "from here", "from my house", "from my home", "from my current location"]
        
        lower = text.lower()
        has_travel_indicator = any(indicator in lower for indicator in travel_indicators)
        has_location_indicator = any(indicator in lower for indicator in location_indicators)
        
        # Also check for direct questions about getting somewhere
        is_direct_question = any(phrase in lower for phrase in [
            "how do i get to", "how to get to", "options to get to", 
            "ways to get to", "best way to get to", "fastest way to get to"
        ])
        
        return (has_travel_indicator and has_location_indicator) or is_direct_question

    def _is_expression_of_gratitude(self, text: str) -> bool:
        """Detect if the user is expressing gratitude."""
        gratitude_expressions = [
            "thank you", "thanks", "thx", "ty", "appreciate it", 
            "much appreciated", "grateful", "great thanks", "cool thanks"
        ]
        lower = text.lower().strip()
        # Check for exact matches or phrases that start with gratitude expressions
        for expr in gratitude_expressions:
            if lower == expr or lower.startswith(expr + " ") or lower.endswith(" " + expr) or f" {expr} " in lower:
                return True
        return False

    def process_command(self, audio_path: str = None, skip_wake_word: bool = False, follow_up_depth: int = 0, pre_transcribed_text: str = None) -> bool:
        """Process a single voice command."""
        if audio_path is None and pre_transcribed_text is None:
            raise ValueError("Either audio_path or pre_transcribed_text must be provided")

        # 1. Speech-to-Text
        if pre_transcribed_text is not None:
            text = pre_transcribed_text
            print(f"\n  🎤 Pilot: \"{text}\"")
        else:
            print("\n  [STT] Transcribing...")
            text = self.stt.transcribe(audio_path)
            if not text or not text.strip():
                print("  ✗ No speech detected.")
                return False
            print(f"  🎤 Pilot: \"{text}\"")

        # Check wake words
        if not skip_wake_word:
            wake_words = self.config["pipeline"].get("wake_words", [])
            if wake_words and not any(ww.lower() in text.lower() for ww in wake_words):
                print(f"  ⏭ Wake word not detected. Ignoring.")
                return False

        # Helper: speak a standby phrase immediately (pre-recorded if available)
        def speak_standby(task: str = "generic"):
            task_key = f"standby_phrases_{task}"
            phrases = self.config["pipeline"].get(task_key) or self.config["pipeline"].get("standby_phrases", ["Copy that, Pilot. Stand by."])
            import random
            phrase = random.choice(phrases)
            print(f"  ⏳ {phrase}")

            # Try pre-recorded clip first
            key = self._normalize_phrase(phrase)
            wav_path = self.standby_clips.get(key)
            if wav_path and Path(wav_path).exists():
                play_audio(wav_path)
                return

            # Fallback: generate on the fly
            wav = self.tts.speak(phrase)
            if wav:
                play_audio(wav)

        # Special handling for gratitude expressions
        if self._is_expression_of_gratitude(text):
            print("  🤖 BT-7274: \"You're welcome, Pilot.\"")
            # Try to play pre-recorded "you're welcome" clip
            key = self._normalize_phrase("you're welcome pilot")
            wav_path = self.standby_clips.get(key)
            if wav_path and Path(wav_path).exists():
                play_audio(wav_path)
            else:
                # Fallback to TTS
                response_wav = self.tts.speak("You're welcome, Pilot.")
                if response_wav:
                    play_audio(response_wav)
            self.last_activity = time.time()
            return True

        # 2. Detect location query and return location directly
        response = None
        if self._is_location_query(text):
            speak_standby("search")
            print("  📍 Locating Pilot...")
            location_result = self.actions.execute("get_location")
            if location_result and not location_result.startswith("Location"):
                print(f"  📍 {location_result}")
                response = f"Pilot, {location_result}"
            else:
                response = "Pilot, my navigation systems are currently unable to establish our position."

        # 3. Detect time query and return time/date directly
        if response is None and self._is_time_query(text):
            speak_standby("generic")
            print("  🕐 Checking chronometer...")
            time_result = self.actions.execute("tell_time")
            date_result = self.actions.execute("tell_date")
            if time_result and date_result:
                print(f"  🕐 {time_result}")
                print(f"  📅 {date_result}")
                response = f"Pilot, {date_result} {time_result}"
            elif time_result:
                response = f"Pilot, {time_result}"
            else:
                response = "Pilot, my chronometer is offline."

        # 4. Detect weather query and fetch from Open-Meteo API
        if response is None and self._is_weather_query(text):
            speak_standby("weather")
            print("  🌤 Fetching local data...")
            # Check if user specified a location in the query
            query_location = self._extract_location_from_query(text)
            if query_location:
                print(f"    📍 Location from query: {query_location}")
                weather_result = self.actions.execute("get_weather_for_location", location=query_location)
            else:
                weather_result = self.actions.execute("get_weather")
            if weather_result and not weather_result.startswith("Weather data unavailable"):
                print(f"  🌤 {weather_result}")
                print("  [LLM] Summarizing for Pilot...")
                summary_prompt = (
                    f"Weather data: {weather_result}\n\n"
                    f"Respond in character as BT-7274 with a detailed, complete explanation. "
                    f"Use 3-7 sentences. Be thorough and helpful. "
                    f"NEVER repeat the user's question. Just answer directly. "
                    f"Only the response text. No quotes, no markdown, no extra text."
                )
                response = self.llm.chat(summary_prompt)
            else:
                response = "Pilot, atmospheric sensors are offline."

        # 5. Detect search intent and perform search BEFORE LLM
        if response is None and self._is_search_query(text):
            speak_standby("search")
            print("  🔍 Looking up...")
            # Enrich query with location context
            enriched_query = self.location.enrich_query(text) if self.location else text
            if enriched_query != text:
                print(f"    📍 Localized query: {enriched_query}")
            search_result = self.actions.execute("search_web", query=enriched_query)
            if search_result and not search_result.startswith("Action") and not search_result.startswith("Search failed"):
                print(f"  🔍 Results: {search_result[:100]}...")
                print("  [LLM] Summarizing for Pilot...")
                # Check if this is a news query
                is_news_query = any(word in text.lower() for word in ["news", "latest", "breaking"])
                if is_news_query:
                    summary_prompt = (
                        f"Search results: {search_result}\n\n"
                        f"Respond in character as BT-7274. Provide a concise summary of the most relevant news. "
                        f"Focus on the key facts from the search results. "
                        f"Use 2-4 sentences. Be direct and informative. "
                        f"NEVER repeat the user's question. Just answer directly. "
                        f"Only the response text. No quotes, no markdown, no extra text."
                    )
                else:
                    summary_prompt = (
                        f"Search results: {search_result}\n\n"
                        f"Respond in character as BT-7274 with a detailed, complete explanation. "
                        f"Use 3-7 sentences. Be thorough and helpful. "
                        f"NEVER repeat the user's question. Just answer directly. "
                        f"Only the response text. No quotes, no markdown, no extra text."
                    )
                response = self.llm.chat(summary_prompt)
            else:
                response = "Pilot, my sensors cannot reach the data network at this time."

        # 6. Special handling for travel/transportation queries
        if response is None and (self._is_travel_query(text) or self._mentions_destination(text) or self._is_requesting_travel_options(text)):
            # For travel queries, get user's location first
            print("  📍 Checking your location for travel planning...")
            location_result = self.actions.execute("get_location_structured")
            if location_result and not location_result.startswith("Location"):
                try:
                    location_data = json.loads(location_result)
                    location_context = f"My current location is: {location_data.get('formatted', 'Unknown')}. Coordinates: {location_data.get('coordinates', {}).get('latitude', 'N/A')}, {location_data.get('coordinates', {}).get('longitude', 'N/A')}. City: {location_data.get('city', 'Unknown')}."
                    # Add location context to the query
                    enriched_text = f"{text} {location_context}"
                    print("  [LLM] Thinking with location context...")
                    response = self.llm.chat(enriched_text)
                except json.JSONDecodeError:
                    # Fallback to simple location if JSON parsing fails
                    simple_location = self.actions.execute("get_location")
                    if simple_location and not simple_location.startswith("Location"):
                        enriched_text = f"{text} My current location is: {simple_location}"
                        print("  [LLM] Thinking with location context...")
                        response = self.llm.chat(enriched_text)
                    else:
                        # Proceed with normal LLM processing if location unavailable
                        print("  [LLM] Thinking...")
                        response = self.llm.chat(text)
            else:
                # Proceed with normal LLM processing if location unavailable
                print("  [LLM] Thinking...")
                response = self.llm.chat(text)
        # 7. Normal LLM Processing (if not a search, weather, or special travel query)
        elif response is None:
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

        # 5. Listen for follow-up if BT asked a question
        max_depth = self.config["pipeline"].get("follow_up", {}).get("max_depth", 1)
        if follow_up_depth < max_depth:
            self._listen_for_follow_up(follow_up_depth)

        return True

    def _listen_for_follow_up(self, follow_up_depth: int):
        """Listen for a follow-up response after BT speaks."""
        timeout = self.config["pipeline"].get("follow_up", {}).get("timeout_seconds", 8)
        stop_phrases = self.config["pipeline"].get("follow_up", {}).get("stop_phrases", ["no", "never mind", "stop", "that's all", "goodbye", "exit", "quit"])

        # Small pause to let speaker echo settle
        time.sleep(0.5)

        print("\n  🎙 Listening for follow-up... (speak now)")
        audio_path = self.recorder.record(max_seconds=timeout) if self.recorder else record_until_silence(self.config["stt"], max_seconds=timeout)

        if not audio_path:
            return

        print("  [STT] Transcribing follow-up...")
        text = self.stt.transcribe(audio_path)

        # Clean up temp file
        try:
            os.remove(audio_path)
        except:
            pass

        if not text or not text.strip():
            print("  ✗ No speech detected in follow-up.")
            return

        text = text.strip()
        print(f"  🎤 Pilot: \"{text}\"")

        # Check for stop phrases (match whole words only)
        import re
        lower_text = text.lower().strip()
        for phrase in stop_phrases:
            # Create a regex pattern that matches the phrase as a whole word
            pattern = r'\b' + re.escape(phrase.lower()) + r'\b'
            if re.search(pattern, lower_text):
                print(f"  ⏭ Follow-up stopped by phrase: '{phrase}'")
                return

        # Process as follow-up command (skip wake word)
        self.process_command(audio_path=None, skip_wake_word=True, follow_up_depth=follow_up_depth + 1, pre_transcribed_text=text)

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
    # Initialize with no preset AI mode so user can choose during startup
    assistant = BT7274Assistant(ai_mode=None)
    assistant.run()


if __name__ == "__main__":
    main()
