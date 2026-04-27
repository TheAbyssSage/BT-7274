#!/usr/bin/env python3
"""
BT-7274 Voice Assistant - Main Pipeline
Microphone → Whisper STT → Ollama LLM → XTTS v2 → Speaker
"""

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

# Setup logging
import logging
import os
from pathlib import Path

# Create logs directory if it doesn't exist
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "bt7274_system.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("BT7274")

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
from tts_fast import StreamingXTTSClient
from actions import ActionHandler
from location import LocationProvider
from utils import play_audio, PersistentAudioRecorder, beep, record_until_silence
from interaction_logger import InteractionLogger


class BT7274Assistant:
    def __init__(self, config_path: str = None, ai_mode: str = "local", performance_mode: str = None):
        if config_path is None:
            config_path = str(Path(__file__).parent / "config.yaml")
        self.config = self.load_config(config_path)
        self.ai_mode = ai_mode  # "local" or "cloud"
        self.performance_mode = performance_mode  # "standard" or "performance"
        self.stt: Optional[WhisperSTT] = None
        self.llm: Optional[OllamaClient] = None
        self.tts: Optional[XTTSClient | StreamingXTTSClient] = None  # Can be XTTSClient or StreamingXTTSClient
        self.actions: Optional[ActionHandler] = None
        self.location: Optional[LocationProvider] = None
        self.recorder: Optional[PersistentAudioRecorder] = None
        self.standby_clips: dict[str, str] = {}  # phrase -> wav_path
        self.running = False
        self.last_activity = time.time()
        self.logger = InteractionLogger()
        
        # Session tracking
        import uuid
        self.session_id = str(uuid.uuid4())[:8]
        self.session_start_time = time.time()
        self.interaction_count = 0
        self.pilot_trust_level = 1
        self.errors_this_session = []
        self.errors_this_interaction = []
        self.actions_this_session = []
        self.weather_context = None
        
    def clear_tts_cache(self):
        """Clear the TTS response cache."""
        if self.tts and hasattr(self.tts, '_response_cache') and self.tts._response_cache is not None:
            cache_count = len(self.tts._response_cache)
            self.tts._response_cache.clear()
            print(f"    ♻️ Cleared {cache_count} cached TTS responses")

    def _report_error(self, component: str, function: str, error: Exception, context: dict = None):
        """Report an error to the current interaction's error list for logging."""
        import traceback
        from datetime import datetime
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "component": component,
            "function": function,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
        }
        if context and isinstance(context, dict):
            error_entry["context"] = context
        self.errors_this_interaction.append(error_entry)
        self.errors_this_session.append(error_entry)
        print(f"    ✗ Error in {component}.{function}: {error}")
        
        # Also log to system log for debugging
        import logging
        logging.error(f"BT-7274 Error - {component}.{function}: {error}", exc_info=True)

    def load_config(self, path: str) -> dict:
        with open(path, 'r') as f:
            return yaml.safe_load(f)

    def initialize(self):
        """Initialize all components."""
        print("=" * 50)
        print("  BT-7274 AI ASSISTANT")
        print("  Protocol 1: Link to Pilot")
        print("=" * 50)

        print("\n[1/9] Initializing Speech-to-Text...")
        try:
            self.stt = WhisperSTT(self.config["stt"])
            # Preload Whisper model to avoid delays during first transcription
            _ = self.stt.model
            print("    ✓ Whisper model loaded and ready.")
        except Exception as e:
            self._report_error("stt", "initialize", e)
            print(f"    ✗ STT initialization failed: {e}")

        print("\n[2/9] Which LLM?")
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

        print(f"\n[3/9] Initializing LLM ({'Local' if self.ai_mode == 'local' else 'Cloud'} Ollama)...")
        try:
            # Use OllamaClient for both local and cloud since they use the same API
            # Merge system prompt from top-level llm config
            llm_config = self.config["llm"][self.ai_mode].copy()
            llm_config["system_prompt"] = self.config["llm"].get("system_prompt", "")
            self.llm = OllamaClient(llm_config)
        except Exception as e:
            self._report_error("llm", "initialize", e)
            print(f"    ✗ LLM initialization failed: {e}")

        print("\n[4/9] Performance Mode Selection")
        if self.performance_mode is None:
            print("  [1] Standard Mode")
            print("      Full response synthesized, then played")
            print("      Best for: Short responses, maximum voice quality")
            print("")
            print("  [2] Performance Mode (STREAMING)")
            print("      Sentence-level streaming with parallel synthesis")
            print("      Best for: Long responses, minimal latency")
            print("      ⚡ First audio plays in ~2-4 seconds")
            print("      ⚡ BT-7274's voice maintained throughout")
            
            while True:
                try:
                    choice = input("\nSelect mode [1-2]: ").strip()
                    if choice == "1":
                        self.performance_mode = "standard"
                        print("  → Selected: Standard Mode")
                        break
                    elif choice == "2":
                        self.performance_mode = "performance"
                        print("  → Selected: Performance Mode (Streaming)")
                        break
                    else:
                        print("  Invalid choice. Please enter 1 or 2.")
                except (EOFError, KeyboardInterrupt):
                    print("\n  Exiting...")
                    sys.exit(0)
        else:
            mode_display = "Standard" if self.performance_mode == "standard" else "Performance (Streaming)"
            print(f"  → Using: {mode_display} (preselected)")

        print(f"\n[5/9] Initializing Text-to-Speech ({self.performance_mode.upper()} MODE)...")
        try:
            if self.performance_mode == "performance":
                self.tts = StreamingXTTSClient(self.config["tts"])
                print("    ⚡ Streaming TTS engine initialized")
                print("    ⚡ Sentence-level parallel synthesis enabled")
            else:
                self.tts = XTTSClient(self.config["tts"])
                print("    ✓ Standard TTS engine initialized")
            
            # Preload TTS model at startup to avoid delays during first synthesis
            self.tts.ensure_ready()
            print("    ✓ TTS model loaded and ready.")
        except Exception as e:
            self._report_error("tts", "initialize", e)
            print(f"    ✗ TTS initialization failed: {e}")

        print("\n[6/9] Checking standby audio files...")
        self._check_and_generate_standby_clips()

        print("\n[7/9] Initializing Action Handler...")
        try:
            self.actions = ActionHandler(self.config["actions"])
        except Exception as e:
            self._report_error("actions", "initialize", e)
            print(f"    ✗ Action handler initialization failed: {e}")

        print("\n[8/9] Initializing Location Services...")
        try:
            manual_loc = self.config.get("location", {}).get("manual")
            self.location = LocationProvider(manual_location=manual_loc)
            if self.location.update():
                print(f"    📍 Location: {self.location.location_str}")
            else:
                print("    ⚠ Location unavailable.")
        except Exception as e:
            self._report_error("location", "initialize", e)
            print(f"    ✗ Location services initialization failed: {e}")

        print("\n[9/9] Opening persistent audio stream...")
        self.recorder = PersistentAudioRecorder(self.config["stt"])
        self.recorder.start()
        print("    ✓ Microphone stream active.")

        print("\n✓ All systems online.")
        if self.performance_mode == "performance":
            print("  ⚡ Performance Mode: Streaming TTS active")
        print("  Say 'Hey BT' or press Enter to speak.\n")

    def _normalize_phrase(self, phrase: str) -> str:
        """Normalize a phrase for dictionary lookup."""
        import re
        phrase = phrase.lower().strip()
        phrase = re.sub(r'[^\w\s]', '', phrase)  # remove punctuation
        phrase = re.sub(r'\s+', ' ', phrase)     # collapse spaces
        return phrase

    def _normalize_filename_to_phrase(self, filename: str) -> str:
        """Convert a filename back to its original phrase."""
        # Remove .wav extension
        phrase = filename.replace('.wav', '')
        # Replace underscores with spaces
        phrase = phrase.replace('_', ' ')
        # Handle special cases for common phrases
        phrase = phrase.replace('you re welcome', "you're welcome")
        return phrase.strip()

    def _check_and_generate_standby_clips(self):
        """Check all standby phrases from config and generate missing .wav files."""
        standby_dir = Path(__file__).parent.parent / "standby"
        standby_dir.mkdir(exist_ok=True)

        # Collect all phrases from config
        all_phrases = []
        pipeline = self.config.get("pipeline", {})
        for key in pipeline:
            if key.startswith("standby_phrases"):
                all_phrases.extend(pipeline[key])

        # Remove duplicates while preserving order
        seen = set()
        unique_phrases = []
        for p in all_phrases:
            if p not in seen:
                seen.add(p)
                unique_phrases.append(p)

        # First pass: check which files exist
        missing = []
        loaded = 0
        for phrase in unique_phrases:
            safe_name = "".join(c if c.isalnum() or c in [' ', '-'] else "_" for c in phrase.lower())
            safe_name = safe_name.replace(" ", "_").replace("-", "_")
            wav_path = standby_dir / f"{safe_name}.wav"
            key = self._normalize_phrase(phrase)

            if wav_path.exists():
                self.standby_clips[key] = str(wav_path)
                loaded += 1
            else:
                missing.append((phrase, safe_name, key))

        # Report status
        total = len(unique_phrases)
        if not missing:
            print(f"    ✓ All {total} standby clips present and loaded.")
            return

        print(f"    ⚠ {len(missing)} of {total} clips missing. Generating now...")

        # Second pass: generate missing files
        generated = 0
        failed = 0
        for phrase, safe_name, key in missing:
            wav_path = standby_dir / f"{safe_name}.wav"
            print(f"    → [{generated + failed + 1}/{len(missing)}] Generating: {phrase}")
            try:
                if self.tts:
                    generated_wav = self.tts.speak(phrase)
                    if generated_wav:
                        import shutil
                        shutil.move(generated_wav, str(wav_path))
                        self.standby_clips[key] = str(wav_path)
                        generated += 1
                        print(f"      ✓ Saved: {wav_path.name}")
                    else:
                        print(f"      ✗ Failed to generate: {phrase}")
                        failed += 1
                else:
                    print(f"      ✗ TTS not initialized: {phrase}")
                    failed += 1
            except Exception as e:
                print(f"      ✗ Error generating '{phrase}': {e}")
                failed += 1

        print(f"    ✓ Standby check complete. Loaded: {loaded}, Generated: {generated}, Failed: {failed}")

    def _extract_location_from_query(self, text: str) -> Optional[str]:
        """Extract location from weather query like 'weather in Tucson, Arizona'."""
        import re
        lower = text.lower()
        # Match patterns like "weather in X", "weather for X", "temperature in X"
        # Exclude common time words/phrases that shouldn't be treated as locations
        time_words = {"today", "tomorrow", "yesterday", "now", "tonight", "next week", "this week", "next few days"}
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

    def _is_forecast_query(self, text: str) -> bool:
        """Detect if the user is asking for a forecast (upcoming weather)."""
        lower = text.lower()
        forecast_keywords = ["forecast", "next week", "next few days", "upcoming", "will it rain", "will it snow", "weekend weather"]
        return any(kw in lower for kw in forecast_keywords)

    def _is_location_query(self, text: str) -> bool:
        """Detect if the user is asking ONLY for their location (not as part of a larger question)."""
        lower = text.lower().strip()
        # Must be a short, direct location query
        location_phrases = ["my location", "where am i", "where are we", "find my location", "what is my location"]
        # Check if the text is primarily a location query (short and contains location keywords)
        is_location = any(kw in lower for kw in location_phrases)
        # If it's a longer query with other intents (travel, weather, etc.), let the LLM handle it
        if is_location and len(lower.split()) > 8:
            return False
        return is_location

    def _is_time_query(self, text: str) -> bool:
        """Detect if the user is asking for the time/date."""
        lower = text.lower().strip()
        time_keywords = ["what time", "what is the time", "current time", "what date", "what is the date", "today's date", "the date today", "what day", "what day is it"]
        return any(kw in lower for kw in time_keywords)

    def _is_search_query(self, text: str) -> bool:
        """Detect if the user is asking for real-time info that needs a web search."""
        lower = text.lower()

        # Don't treat weather queries as search queries
        if self._is_weather_query(text):
            return False

        search_keywords = [
            "who won", "who was",
            "news", "latest",
            "search", "look up", "tell me about", "find", "what is", "what are"
        ]
        
        # Check for basic search keywords
        if any(kw in lower for kw in search_keywords):
            return True
            
        # Check for event/datetime questions that likely need current info
        event_keywords = ["when is", "when was", "what year", "what date", "next", "upcoming", "recent", "price", "cost", "ticket", "how much", "order"]
        has_event_keyword = any(kw in lower for kw in event_keywords)
        
        # Check for specific topics that change over time
        time_sensitive_topics = ["comic con", "conference", "event", "concert", "festival", "tournament", "election", "release", "show"]
        has_time_sensitive_topic = any(topic in lower for topic in time_sensitive_topics)
        
        # If asking about when something happens and it's time-sensitive, it needs search
        if has_event_keyword and has_time_sensitive_topic:
            return True
            
        # Also check for general event information queries
        if self._is_event_information_query(text):
            return True
            
        return False

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
        
        # Don't treat event information queries as travel queries
        if self._is_event_information_query(text):
            return False
            
        return any(kw in lower for kw in travel_keywords)

    def _is_travel_query_complex(self, text: str) -> bool:
        """Detect if the user is asking about travel in a complex query."""
        lower = text.lower()
        
        # Don't treat event information queries as travel queries
        if self._is_event_information_query(text):
            return False
        
        # Check for travel-related words combined with destinations
        travel_indicators = ["how", "way", "route", "get", "travel", "journey"]
        has_travel_word = any(indicator in lower for indicator in travel_indicators)
        
        # Check if asking about getting somewhere specific
        getting_indicators = ["to brussels", "to antwerp", "to belgium", "getting to", "go to"]
        has_getting_phrase = any(phrase in lower for phrase in getting_indicators)
        
        return has_travel_word and has_getting_phrase

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
        # Don't treat event information queries as travel queries
        if self._is_event_information_query(text):
            return False
        
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

    def _is_event_information_query(self, text: str) -> bool:
        """Detect if the user is asking for event information (dates, prices, etc.)"""
        lower = text.lower()
        # Keywords that indicate the user wants information rather than travel
        information_keywords = ["when", "price", "cost", "ticket", "how much", "date", "time", "order"]
        # Topics that are often events
        event_topics = ["comic con", "concert", "festival", "conference", "expo", "event", "show"]
        
        has_info_keyword = any(keyword in lower for keyword in information_keywords)
        has_event_topic = any(topic in lower for topic in event_topics)
        
        return has_info_keyword and has_event_topic

    def generate_standby_responses(self, force_regenerate: bool = False):
        """Generate standby response audio files using BT's voice.
        
        Args:
            force_regenerate: If True, regenerate all clips even if they exist.
        """
        print("Generating standby responses with BT's voice...")
        
        # Collect all phrases from config
        all_phrases = []
        pipeline = self.config.get("pipeline", {})
        for key in pipeline:
            if key.startswith("standby_phrases"):
                all_phrases.extend(pipeline[key])
        
        # Add common response patterns for better caching coverage
        common_responses = [
            "Processing complete, Pilot.",
            "Operation complete, Pilot.",
            "Task completed, Pilot.",
            "Execution successful, Pilot.",
            "Sequence complete, Pilot.",
            "Protocol fulfilled, Pilot.",
            "Mission accomplished, Pilot.",
            "Objective achieved, Pilot."
        ]
        all_phrases.extend(common_responses)
        
        # Remove duplicates while preserving order
        seen = set()
        phrases = []
        for p in all_phrases:
            if p not in seen:
                seen.add(p)
                phrases.append(p)
        
        generated_count = 0
        skipped_count = 0
        output_dir = Path(__file__).parent.parent / "standby"
        output_dir.mkdir(exist_ok=True)
        
        for phrase in phrases:
            # Create safe filename
            safe_name = "".join(c if c.isalnum() or c in [' ', '-'] else "_" for c in phrase.lower())
            safe_name = safe_name.replace(" ", "_").replace("-", "_")
            output_path = output_dir / f"{safe_name}.wav"
            
            if output_path.exists() and not force_regenerate:
                print(f"  ⏭ Skipping: {phrase}")
                skipped_count += 1
                continue
                
            print(f"  → Generating: {phrase}")
            try:
                # Remove old file if forcing regeneration
                if output_path.exists() and force_regenerate:
                    output_path.unlink()
                    
                wav_path = self.tts.speak(phrase) if self.tts else None
                if wav_path:
                    import shutil
                    shutil.move(wav_path, str(output_path))
                    print(f"    ✓ Saved: {output_path.name}")
                    generated_count += 1
                else:
                    print(f"    ✗ Failed: {phrase}")
            except Exception as e:
                print(f"    ✗ Error generating '{phrase}': {e}")
        
        print(f"\nDone! Generated: {generated_count}, Skipped: {skipped_count}")
        return generated_count

    def process_command(self, audio_path: str = None, skip_wake_word: bool = False, follow_up_depth: int = 0, pre_transcribed_text: str = None) -> bool:
        """Process a single voice command."""
        if audio_path is None and pre_transcribed_text is None:
            raise ValueError("Either audio_path or pre_transcribed_text must be provided")

        # 1. Speech-to-Text
        stt_confidence = None
        if pre_transcribed_text is not None:
            text = pre_transcribed_text
            print(f"\n  🎤 Pilot: \"{text}\"")
        else:
            print("\n  [STT] Transcribing...")
            try:
                stt_result = self.stt.transcribe(audio_path) if self.stt else {"text": "", "confidence": 0.0}
                text = stt_result.get("text", "") if isinstance(stt_result, dict) else str(stt_result)
                stt_confidence = stt_result.get("confidence") if isinstance(stt_result, dict) else None
            except Exception as e:
                self._report_error("stt", "transcribe", e, {"audio_path": audio_path})
                text = ""
                stt_confidence = 0.0
            if not text or not text.strip():
                print("  ✗ No speech detected.")
                return False
            print(f"  🎤 Pilot: \"{text}\"")
            
            # Confidence-based filtering for noisy environments
            min_confidence = self.config["stt"].get("min_confidence", 0.3)
            if stt_confidence is not None and stt_confidence < min_confidence:
                print(f"  ⚠ Low confidence transcription ({stt_confidence:.2f}). Treating as noise.")
                return False

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
            if self.tts:
                wav = self.tts.speak(phrase)
                if wav:
                    play_audio(wav)
                
        # Helper: try to find a suitable standby clip for common responses
        def try_standby_for_response(response_text: str) -> Optional[str]:
            """Try to match a response to a pre-generated standby clip."""
            if not response_text:
                return None
                
            normalized = self._normalize_phrase(response_text)
            
            # Direct match
            if normalized in self.standby_clips:
                return self.standby_clips[normalized]
                
            # Partial matches for common patterns
            common_patterns = {
                "you're welcome": ["thank you", "thanks", "thx"],
                "copy that": ["acknowledged", "understood", "roger"],
                "stand by": ["standby", "waiting", "processing"],
                "retrieving": ["fetching", "accessing", "pulling"],
                "pilot": ["user", "human", "person"]
            }
            
            for standby_key, patterns in common_patterns.items():
                for pattern in patterns:
                    if pattern in normalized:
                        # Look for a standby clip that contains this pattern
                        for key, path in self.standby_clips.items():
                            if standby_key in key and Path(path).exists():
                                return path
                                
            return None

        # Special handling for gratitude expressions
        if self._is_expression_of_gratitude(text):
            print("  🤖 BT-7274: \"You're welcome, Pilot.\"")
            # Try to play pre-recorded "you're welcome" clip
            key = self._normalize_phrase("you're welcome pilot")
            wav_path = self.standby_clips.get(key)
            if wav_path and Path(wav_path).exists():
                play_audio(wav_path)
            else:
                # Try other variations of gratitude responses
                gratitude_variations = [
                    "you're welcome pilot",
                    "you're welcome",
                    "my pleasure pilot",
                    "glad to assist pilot",
                    "happy to help pilot",
                    "anytime pilot"
                ]
                
                found_clip = False
                for variation in gratitude_variations:
                    var_key = self._normalize_phrase(variation)
                    var_path = self.standby_clips.get(var_key)
                    if var_path and Path(var_path).exists():
                        play_audio(var_path)
                        found_clip = True
                        break
                        
                if not found_clip:
                    # Fallback to TTS
                    if self.tts:
                        response_wav = self.tts.speak("You're welcome, Pilot.")
                        if response_wav:
                            play_audio(response_wav)
            self.last_activity = time.time()
            return True

        # 2. Handle compound queries - detect all matching query types
        response_parts = []
        handled_types = set()
        
        # Check for location query (but not if part of longer question)
        if self._is_location_query(text):
            print("  📍 Locating Pilot...")
            try:
                location_result = self.actions.execute("get_location") if self.actions else "Location unavailable"
                if location_result and not location_result.startswith("Location"):
                    print(f"  📍 {location_result}")
                    response_parts.append(f"Pilot, {location_result}")
                    handled_types.add("location")
                else:
                    response_parts.append("Pilot, my navigation systems are currently unable to establish our position.")
                    handled_types.add("location")
            except Exception as e:
                self._report_error("actions", "get_location", e)
                response_parts.append("Pilot, my navigation systems are currently unable to establish our position.")
                handled_types.add("location")

        # Check for time query
        if self._is_time_query(text):
            print("  🕐 Checking chronometer...")
            try:
                time_result = self.actions.execute("tell_time") if self.actions else "Time unavailable"
                date_result = self.actions.execute("tell_date") if self.actions else "Date unavailable"
                if time_result and date_result:
                    print(f"  🕐 {time_result}")
                    print(f"  📅 {date_result}")
                    response_parts.append(f"Pilot, {date_result} {time_result}")
                    handled_types.add("time")
                elif time_result:
                    response_parts.append(f"Pilot, {time_result}")
                    handled_types.add("time")
                else:
                    response_parts.append("Pilot, my chronometer is offline.")
                    handled_types.add("time")
            except Exception as e:
                self._report_error("actions", "tell_time/date", e)
                response_parts.append("Pilot, my chronometer is offline.")
                handled_types.add("time")

        # Check for weather query
        if self._is_weather_query(text):
            print("  🌤 Fetching local data...")
            try:
                # Check if user specified a location in the query
                query_location = self._extract_location_from_query(text)
                is_forecast = self._is_forecast_query(text)

                if is_forecast:
                    # Use forecast action
                    if query_location:
                        print(f"    📍 Location from query: {query_location}")
                        weather_result = self.actions.execute("get_weather_forecast", location=query_location) if self.actions else "Weather unavailable"
                    else:
                        weather_result = self.actions.execute("get_weather_forecast") if self.actions else "Weather unavailable"
                else:
                    # Use current weather action
                    if query_location:
                        print(f"    📍 Location from query: {query_location}")
                        weather_result = self.actions.execute("get_weather_for_location", location=query_location) if self.actions else "Weather unavailable"
                    else:
                        weather_result = self.actions.execute("get_weather") if self.actions else "Weather unavailable"

                if weather_result and not weather_result.startswith("Weather data unavailable") and not weather_result.startswith("Forecast data unavailable"):
                    print(f"  🌤 {weather_result}")
                    print("  [LLM] Summarizing for Pilot...")
                    summary_prompt = (
                        f"Weather data: {weather_result}\n\n"
                        f"Respond in character as BT-7274 with a detailed, complete explanation. "
                        f"Use 3-7 sentences. Be thorough and helpful. "
                        f"NEVER repeat the user's question. Just answer directly. "
                        f"Only the response text. No quotes, no markdown, no extra text."
                    )
                    try:
                        weather_response = self.llm.chat(summary_prompt) if self.llm else f"Failed to summarize weather: {weather_result}"
                        response_parts.append(weather_response)
                    except Exception as e:
                        self._report_error("llm", "chat_weather_summary", e)
                        response_parts.append(f"Pilot, {weather_result}")
                    handled_types.add("weather")
                else:
                    response_parts.append("Pilot, atmospheric sensors are offline.")
                    handled_types.add("weather")
            except Exception as e:
                self._report_error("actions", "get_weather", e)
                response_parts.append("Pilot, atmospheric sensors are offline.")
                handled_types.add("weather")

        # Check for search intent - always let LLM handle these with search results
        if self._is_search_query(text) and "search" not in handled_types:
            print("  🔍 Looking up...")
            try:
                # Enrich query with location context
                enriched_query = self.location.enrich_query(text) if self.location else text
                if enriched_query != text:
                    print(f"    📍 Localized query: {enriched_query}")
                search_result = self.actions.execute("search_web", query=enriched_query) if self.actions else "Search unavailable"
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
                    try:
                        search_response = self.llm.chat(summary_prompt) if self.llm else f"Failed to summarize search: {search_result}"
                        response_parts.append(search_response)
                    except Exception as e:
                        self._report_error("llm", "chat_search_summary", e)
                        response_parts.append(f"Pilot, {search_result}")
                    handled_types.add("search")
                else:
                    response_parts.append("Pilot, my sensors cannot reach the data network at this time.")
                    handled_types.add("search")
            except Exception as e:
                self._report_error("actions", "search_web", e)
                response_parts.append("Pilot, my sensors cannot reach the data network at this time.")
                handled_types.add("search")

        # Check for TTS cache clearing request
        if "clear tts cache" in text.lower() or "clear cache" in text.lower():
            print("  ♻️ Clearing TTS cache...")
            self.clear_tts_cache()
            response_parts.append("TTS cache cleared, Pilot.")
            handled_types.add("maintenance")

        # Check for travel queries - always let LLM handle these with location context
        # But don't process travel context for event information queries (dates, prices, etc.)
        is_information_query = self._is_event_information_query(text)
        is_travel_related = (self._is_travel_query(text) or self._mentions_destination(text) or 
                           self._is_requesting_travel_options(text) or self._is_travel_query_complex(text))
        
        if is_travel_related and "travel" not in handled_types and not is_information_query:
            # For travel queries, silently get user's location and inject it into the LLM prompt
            print("  📍 Checking your location for travel planning...")
            location_result = self.actions.execute("get_location_structured") if self.actions else "Location unavailable"
            if location_result and not location_result.startswith("Location"):
                try:
                    location_data = json.loads(location_result)
                    location_context = f"IMPORTANT PILOT LOCATION DATA - USE THIS EXACT LOCATION, DO NOT ASSUME ANY OTHER LOCATION: {location_data.get('formatted', 'Unknown')}. Coordinates: {location_data.get('coordinates', {}).get('latitude', 'N/A')}, {location_data.get('coordinates', {}).get('longitude', 'N/A')}. City: {location_data.get('city', 'Unknown')}."
                    # Add location context to the query - let LLM handle the full question
                    enriched_text = f"{text} {location_context} DO NOT MENTION GAME WORLD LOCATIONS OR FICTIONAL PLACES. USE THE PROVIDED REAL-WORLD GEOGRAPHIC INFORMATION."
                    print("  [LLM] Thinking with location context...")
                    travel_response = self.llm.chat(enriched_text) if self.llm else "Travel information unavailable"
                    response_parts.append(travel_response)
                    handled_types.add("travel")
                except json.JSONDecodeError:
                    # Fallback to simple location if JSON parsing fails
                    simple_location = self.actions.execute("get_location") if self.actions else "Location unavailable"
                    if simple_location and not simple_location.startswith("Location"):
                        enriched_text = f"{text} IMPORTANT PILOT LOCATION DATA - USE THIS EXACT LOCATION, DO NOT ASSUME ANY OTHER LOCATION: {simple_location} DO NOT MENTION GAME WORLD LOCATIONS OR FICTIONAL PLACES. USE THE PROVIDED REAL-WORLD GEOGRAPHIC INFORMATION."
                        print("  [LLM] Thinking with location context...")
                        travel_response = self.llm.chat(enriched_text) if self.llm else "Travel information unavailable"
                        response_parts.append(travel_response)
                        handled_types.add("travel")
                    else:
                        print("  [LLM] Thinking...")
                        normal_response = self.llm.chat(text) if self.llm else "Response unavailable"
                        response_parts.append(normal_response)
                        handled_types.add("travel")
            else:
                print("  [LLM] Thinking...")
                normal_response = self.llm.chat(text) if self.llm else "Response unavailable"
                response_parts.append(normal_response)
                handled_types.add("travel")
        elif is_information_query and "travel" not in handled_types and is_travel_related:
            # For event information queries, process normally without location context
            print("  [LLM] Thinking...")
            normal_response = self.llm.chat(text) if self.llm else "Response unavailable"
            response_parts.append(normal_response)
            handled_types.add("travel")

        # Combine responses or fall back to normal processing
        llm_response_time = None
        if response_parts:
            # Combine all collected responses
            response = " ".join(response_parts)
        elif not handled_types:
            # No specific handlers matched, use normal LLM processing
            print("  [LLM] Thinking...")
            llm_start = time.time()
            try:
                response = self.llm.chat(text) if self.llm else "Response unavailable"
            except Exception as e:
                self._report_error("llm", "chat", e, {"pilot_message": text})
                response = "Pilot, my neural network is experiencing interference. Please try again."
            llm_response_time = time.time() - llm_start
        else:
            # This shouldn't happen, but just in case
            response = "Processing complete, Pilot."

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
        
        # Optimize response for TTS - break into smaller segments for better pacing
        # This helps with long responses that might cause TTS delays
        if len(clean_response) > 300:
            # Look for sentence boundaries to break the response
            sentences = re.split(r'(?<=[.!?])\s+', clean_response)
            if len(sentences) > 1:
                # Join sentences until we get reasonable chunks
                optimized_segments = []
                current_segment = ""
                
                for sentence in sentences:
                    if len(current_segment) + len(sentence) < 200:
                        current_segment += " " + sentence if current_segment else sentence
                    else:
                        if current_segment:
                            optimized_segments.append(current_segment)
                        current_segment = sentence
                        
                if current_segment:
                    optimized_segments.append(current_segment)
                    
                # If we have multiple segments, consider playing them separately
                # for better responsiveness (but we'll keep as single for now)
                if len(optimized_segments) > 1:
                    # Could implement staggered playback here if needed
                    pass
        
        # Post-process to correct location inaccuracies
        if "New London" in clean_response:
            # Try to get actual location and replace New London references
            try:
                from location import LocationProvider
                loc = LocationProvider()
                if loc.update():
                    actual_location = loc.location_str
                    clean_response = clean_response.replace("New London", actual_location)
            except:
                pass
        
        if not clean_response:
            clean_response = "Processing complete, Pilot."

        print(f"  🤖 BT-7274: \"{clean_response}\"")

        # 4. Text-to-Speech
        print("  [TTS] Synthesizing voice...")

        # Try to use a standby clip for common responses to reduce latency
        standby_wav = try_standby_for_response(clean_response)
        tts_success = False
        if standby_wav and Path(standby_wav).exists():
            print("    ♻️ Using pre-generated standby clip")
            try:
                play_audio(standby_wav)
                tts_success = True
            except Exception as e:
                self._report_error("tts", "play_standby", e, {"standby_wav": standby_wav})
        else:
            # Use appropriate TTS method based on performance mode
            try:
                if self.performance_mode == "performance" and self.tts:
                    # Performance mode: Use streaming TTS for sentence-level playback
                    print("    ⚡ Streaming TTS (sentence-level)...")
                    if self.tts and hasattr(self.tts, 'speak_streaming') and callable(getattr(self.tts, 'speak_streaming', None)):
                        try:
                            self.tts.speak_streaming(clean_response)
                            tts_success = True
                        except Exception as e:
                            self._report_error("tts", "speak_streaming", e, {"text": clean_response})
                            tts_success = False
                    elif self.tts and hasattr(self.tts, 'speak') and callable(getattr(self.tts, 'speak', None)):
                        # Fallback to standard TTS if streaming not available
                        try:
                            output_wav = self.tts.speak(clean_response)
                            if output_wav:
                                try:
                                    play_audio(output_wav)
                                    tts_success = True
                                except Exception as play_error:
                                    self._report_error("tts", "play_audio", play_error, {"output_wav": output_wav})
                                    tts_success = False
                        except Exception as e:
                            self._report_error("tts", "speak", e, {"text": clean_response})
                            tts_success = False
                    else:
                        # Fallback to standard TTS if streaming not available
                        output_wav = self.tts.speak(clean_response) if self.tts else None
                        if output_wav:
                            try:
                                play_audio(output_wav)
                                tts_success = True
                            except Exception as play_error:
                                self._report_error("tts", "play_audio", play_error, {"output_wav": output_wav})
                elif self.tts:
                    # Standard mode: Full response synthesis then playback
                    output_wav = self.tts.speak(clean_response) if self.tts else None
                    if output_wav:
                        try:
                            play_audio(output_wav)
                            tts_success = True
                        except Exception as e:
                            self._report_error("tts", "play_audio", e, {"output_wav": output_wav})
            except Exception as e:
                self._report_error("tts", "speak", e, {"text": clean_response})

        # Log the interaction (after TTS so metrics are accurate)
        tts_metrics = getattr(self.tts, 'get_metrics', lambda: {})() if self.tts else {}
        
        # Determine cache hit type
        cache_hit = None
        if standby_wav and Path(standby_wav).exists():
            cache_hit = "standby_clip"
        elif tts_metrics and tts_metrics.get("cached"):
            cache_hit = "tts_cache"
        
        # Get audio file path
        audio_file_path = None
        output_wav = None  # Initialize to prevent unbound variable error
        if not (standby_wav and Path(standby_wav).exists()):
            if self.performance_mode == "performance":
                audio_file_path = "streaming"
            else:
                audio_file_path = output_wav if 'output_wav' in locals() and output_wav else None
        
        # Get location context
        location_context = None
        if self.location and self.location.location_str:
            location_context = self.location.location_str
        
        # Get weather context (if weather was queried)
        weather_context = None
        weather_result = None  # Initialize to prevent unbound variable error
        if "weather" in handled_types:
            weather_context = weather_result if 'weather_result' in locals() and weather_result else None
        
        # Calculate mission elapsed time
        mission_elapsed_time = time.time() - self.session_start_time
        
        # Calculate conversation duration (time since last interaction)
        conversation_duration = time.time() - self.last_activity
        
        # Increment interaction count and update trust level
        self.interaction_count += 1
        if self.interaction_count > 10:
            self.pilot_trust_level = min(5, self.pilot_trust_level + 1)
        
        # Determine protocol reference based on interaction type
        protocol_reference = "Protocol 1: Link to Pilot"
        if "weather" in handled_types or "location" in handled_types:
            protocol_reference = "Protocol 2: Uphold the Mission"
        elif any(err in str(handled_types) for err in ["error", "fail"]):
            protocol_reference = "Protocol 3: Protect the Pilot"
        
        # Collect errors (only those from this interaction)
        errors = self.errors_this_interaction if self.errors_this_interaction else None
        
        # Collect actions executed
        actions_executed = list(handled_types) if handled_types else None
        
        # Get wake word used
        wake_word = None
        if not skip_wake_word:
            wake_words = self.config["pipeline"].get("wake_words", [])
            for ww in wake_words:
                if ww.lower() in text.lower():
                    wake_word = ww
                    break
        
        self.logger.log_interaction(
            pilot_message=text,
            bt_response=clean_response,
            interaction_type="voice",
            ai_mode=self.ai_mode,
            performance_mode=self.performance_mode,
            tts_metrics=tts_metrics if tts_metrics else None,
            llm_response_time=llm_response_time if 'llm_response_time' in locals() else None,
            stt_confidence=stt_confidence,
            audio_file_path=audio_file_path,
            cache_hit=cache_hit,
            token_usage=None,  # Ollama doesn't expose token usage easily
            wake_word=wake_word,
            follow_up_depth=follow_up_depth,
            session_id=self.session_id,
            conversation_duration=conversation_duration,
            protocol_reference=protocol_reference,
            pilot_trust_level=self.pilot_trust_level,
            mission_elapsed_time=mission_elapsed_time,
            actions_executed=actions_executed,
            errors=errors,
            location_context=location_context,
            weather_context=weather_context,
            metadata={
                "handled_types": list(handled_types) if 'handled_types' in locals() else [],
            },
        )

        self.last_activity = time.time()

        # Clear per-interaction errors for the next turn
        self.errors_this_interaction = []

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
        stt_result = self.stt.transcribe(audio_path) if self.stt else {"text": "", "confidence": 0.0}
        text = stt_result.get("text", "") if isinstance(stt_result, dict) else str(stt_result)

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

        # Check for gratitude expressions FIRST (before stop phrases)
        if self._is_expression_of_gratitude(text):
            print("  🤖 BT-7274: \"You're welcome, Pilot.\"")
            # Try to play pre-recorded "you're welcome" clip
            key = self._normalize_phrase("you're welcome pilot")
            wav_path = self.standby_clips.get(key)
            if wav_path and Path(wav_path).exists():
                play_audio(wav_path)
            else:
                # Try other variations of gratitude responses
                gratitude_variations = [
                    "you're welcome pilot",
                    "you're welcome",
                    "my pleasure pilot",
                    "glad to assist pilot",
                    "happy to help pilot",
                    "anytime pilot"
                ]
                
                found_clip = False
                for variation in gratitude_variations:
                    var_key = self._normalize_phrase(variation)
                    var_path = self.standby_clips.get(var_key)
                    if var_path and Path(var_path).exists():
                        play_audio(var_path)
                        found_clip = True
                        break
                        
                if not found_clip:
                    # Fallback to TTS
                    response_wav = self.tts.speak("You're welcome, Pilot.")
                    if response_wav:
                        play_audio(response_wav)
            self.last_activity = time.time()
            # After gratitude, listen for another follow-up
            if follow_up_depth < self.config["pipeline"].get("follow_up", {}).get("max_depth", 1):
                self._listen_for_follow_up(follow_up_depth)
            return

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
    import argparse
    parser = argparse.ArgumentParser(description="BT-7274 Voice Assistant")
    parser.add_argument("--generate-responses", action="store_true", 
                        help="Generate missing standby response audio files")
    parser.add_argument("--force-regenerate", action="store_true", 
                        help="Force regenerate ALL standby audio files")
    parser.add_argument("--ai-mode", choices=["local", "cloud"], 
                        help="AI mode (local or cloud)")
    parser.add_argument("--performance-mode", choices=["standard", "performance"], 
                        help="TTS mode (standard or performance)")
    args = parser.parse_args()
    
    # Initialize with no preset modes so user can choose during startup
    assistant = BT7274Assistant(ai_mode=args.ai_mode, performance_mode=args.performance_mode)
    
    if args.generate_responses or args.force_regenerate:
        # Initialize all components first
        assistant.initialize()
        count = assistant.generate_standby_responses(force_regenerate=args.force_regenerate)
        print(f"Successfully generated {count} standby responses!")
        return
    
    assistant.run()


if __name__ == "__main__":
    main()
