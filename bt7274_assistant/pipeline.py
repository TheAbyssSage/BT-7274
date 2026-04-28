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
system_log_dir = log_dir / "system_logs"
system_log_dir.mkdir(exist_ok=True)

# Configure logging with daily files
from datetime import datetime as _datetime
_system_log_file = system_log_dir / f"bt7274_system_{_datetime.now().strftime('%Y-%m-%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(_system_log_file),
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

# For semantic similarity matching
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SEMANTIC_SIMILARITY_AVAILABLE = True
except ImportError:
    SEMANTIC_SIMILARITY_AVAILABLE = False
    logger.warning("Semantic similarity matching not available. Install scikit-learn for this feature.")

# Import our modules
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
from stt import WhisperSTT
from llm import OllamaClient, CloudLLMClient
from tts import XTTSClient
from tts_fast import StreamingXTTSClient
from bt7274_workstation.actions import ActionHandler
from bt7274_workstation.location import LocationProvider
from utils import play_audio, PersistentAudioRecorder, beep, record_until_silence
from bt7274_workstation.interaction_logger import InteractionLogger
from bt7274_workstation.battery_monitor import BatteryMonitor
from bt7274_workstation.weather_monitor import WeatherMonitor
from bt7274_workstation.vpn_monitor import VPNMonitor
from bt7274_workstation.protocol_brief import ProtocolBrief
from bt7274_workstation.session_cache_manager import (
    get_session_cache,
    save_semantic_vectors,
    load_semantic_vectors,
    save_session_state,
    load_session_state,
    archive_and_clear_session,
)
from ui import header, section, sub_section, info, success, warning, error, status, bullet, spacer, divider, footer, prompt, choice_menu, box, progress, quote, log_system, log_stt, log_llm, log_tts, log_action, cache_hit, clip_play, listening, goodbye


class BT7274Assistant:
    def __init__(self, config_path: Optional[str] = None, ai_mode: str = "local", performance_mode: Optional[str] = None):
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
        self.bt_clips: dict[str, str] = {}  # phrase -> wav_path for BT's original lines
        self.bt_clip_texts: dict[str, str] = {}  # filename -> original text for BT's lines
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
        self.battery: Optional[BatteryMonitor] = None
        self.weather: Optional[WeatherMonitor] = None
        self.vpn: Optional[VPNMonitor] = None
        
        # Protocol Mode
        self.protocol_mode_enabled: bool = self.config.get("protocol_mode", {}).get("enabled", False)
        self.protocol_brief: Optional[ProtocolBrief] = None
        
        # For semantic similarity matching
        self.semantic_vectorizer = None
        self.semantic_clip_matrix = None
        self.semantic_clip_phrases = []
        
        # For context-aware phrase selection
        self.conversation_history = []  # List of (user_query, bot_response) tuples
        self.current_context = {}       # Current context information
        
        # For personality-based response weighting
        self.personality_weights = {
            "loyalty": 1.0,      # Increases with pilot trust
            "formality": 0.8,    # BT is generally formal
            "tactical": 0.9,     # BT is tactical/military
            "humor": 0.3,        # BT has dry humor
            "urgency": 0.5       # Depends on situation
        }
        
        # For dialogue trees
        self.dialogue_state = "idle"    # Current dialogue state
        self.dialogue_history = []      # Track dialogue tree progress
        self.available_transitions = {} # Possible next lines in dialogue
        
    def clear_tts_cache(self):
        """Clear the TTS response cache."""
        if self.tts and hasattr(self.tts, '_response_cache') and self.tts._response_cache is not None:
            cache_count = len(self.tts._response_cache)
            self.tts._response_cache.clear()
            cache_hit(f"Cleared {cache_count} cached TTS responses")

    def _report_error(self, component: str, function: str, exc: Exception, context: Optional[dict] = None):
        """Report an error to the current interaction's error list for logging."""
        import traceback
        from datetime import datetime
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "component": component,
            "function": function,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
        }
        if context and isinstance(context, dict):
            error_entry["context"] = context
        self.errors_this_interaction.append(error_entry)
        self.errors_this_session.append(error_entry)
        error(f"Error in {component}.{function}: {exc}")
        
        # Also log to system log for debugging
        import logging
        logging.error(f"BT-7274 Error - {component}.{function}: {exc}", exc_info=True)

    def _save_session_state(self):
        """Persist current session metadata to session cache."""
        try:
            state = {
                "session_id": self.session_id,
                "session_start_time": self.session_start_time,
                "session_end_time": time.time(),
                "interaction_count": self.interaction_count,
                "pilot_trust_level": self.pilot_trust_level,
                "errors_this_session": self.errors_this_session,
                "actions_this_session": self.actions_this_session,
                "conversation_history": self.conversation_history,
                "current_context": self.current_context,
                "dialogue_state": self.dialogue_state,
                "dialogue_history": self.dialogue_history,
                "personality_weights": self.personality_weights,
                "weather_context": self.weather_context,
                "protocol_mode_enabled": self.protocol_mode_enabled,
            }
            save_session_state(state)
        except Exception as e:
            warning(f"Failed to save session state: {e}")

    def load_config(self, path: str) -> dict:
        with open(path, 'r') as f:
            return yaml.safe_load(f)

    def _ensure_log_directories(self):
        """Ensure all required log directories exist at startup."""
        base_log_dir = Path(__file__).parent.parent / "logs"
        required_dirs = [
            base_log_dir,
            base_log_dir / "bt-pilot_interactions",
            base_log_dir / "bt_logs",
            base_log_dir / "system_logs",
            base_log_dir / "pilot_logs",
            base_log_dir / "pilot_health",
            base_log_dir / "bt_workstation",
            base_log_dir / "bt_brief",
            base_log_dir / "pilot_voice_commands",
            base_log_dir / "bt_vision",
        ]
        for dir_path in required_dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
            if not dir_path.exists():
                error(f"Failed to create log directory: {dir_path}")

    def initialize(self):
        """Initialize all components."""
        header("BT-7274 AI ASSISTANT  |  Protocol 1: Link to Pilot")

        section("[0/10] Checking log directories")
        self._ensure_log_directories()
        success("Log directories verified.")

        section("[1/10] Initializing Speech-to-Text")
        try:
            self.stt = WhisperSTT(self.config["stt"])
            # Preload Whisper model to avoid delays during first transcription
            _ = self.stt.model
            success("Whisper model loaded and ready.")
        except Exception as e:
            self._report_error("stt", "initialize", e)
            error(f"STT initialization failed: {e}")

        section("[2/10] Which LLM?")
        if self.ai_mode is None:
            # Simple and reliable model selection
            local_model = self.config["llm"]["local"]["model"]
            cloud_model = self.config["llm"]["cloud"]["model"]

            info(f"[1] Local Ollama  ({local_model})")
            info(f"[2] Cloud Ollama  ({cloud_model})")

            while True:
                try:
                    choice = prompt("Select model [1-2]:")
                    if choice == "1":
                        self.ai_mode = "local"
                        status("SELECT", f"Local Ollama ({local_model})")
                        break
                    elif choice == "2":
                        self.ai_mode = "cloud"
                        status("SELECT", f"Cloud Ollama ({cloud_model})")
                        break
                    else:
                        warning("Invalid choice. Please enter 1 or 2.")
                except (EOFError, KeyboardInterrupt):
                    info("Exiting...")
                    sys.exit(0)
        else:
            # Use the provided AI mode
            mode_name = "Local Ollama" if self.ai_mode == "local" else "Cloud Ollama"
            model_name = self.config["llm"][self.ai_mode]["model"]
            status("USING", f"{mode_name} ({model_name}) (preselected)")

        section(f"[3/10] Initializing LLM ({'Local' if self.ai_mode == 'local' else 'Cloud'} Ollama)")
        try:
            # Use OllamaClient for both local and cloud since they use the same API
            # Merge system prompt from top-level llm config
            llm_config = self.config["llm"][self.ai_mode].copy()
            llm_config["system_prompt"] = self.config["llm"].get("system_prompt", "")
            self.llm = OllamaClient(llm_config)
        except Exception as e:
            self._report_error("llm", "initialize", e)
            error(f"LLM initialization failed: {e}")

        section("[4/10] Performance Mode Selection")
        if self.performance_mode is None:
            info("[1] Standard Mode")
            info("    Full response synthesized, then played")
            info("    Best for: Short responses, maximum voice quality")
            spacer()
            info("[2] Performance Mode (STREAMING)")
            info("    Sentence-level streaming with parallel synthesis")
            info("    Best for: Long responses, minimal latency")
            info("    First audio plays in ~2-4 seconds")
            info("    BT-7274's voice maintained throughout")

            while True:
                try:
                    choice = prompt("Select mode [1-2]:")
                    if choice == "1":
                        self.performance_mode = "standard"
                        status("SELECT", "Standard Mode")
                        break
                    elif choice == "2":
                        self.performance_mode = "performance"
                        status("SELECT", "Performance Mode (Streaming)")
                        break
                    else:
                        warning("Invalid choice. Please enter 1 or 2.")
                except (EOFError, KeyboardInterrupt):
                    info("Exiting...")
                    sys.exit(0)
        else:
            mode_display = "Standard" if self.performance_mode == "standard" else "Performance (Streaming)"
            status("USING", f"{mode_display} (preselected)")

        section(f"[5/10] Initializing Text-to-Speech ({self.performance_mode.upper()} MODE)")
        try:
            if self.performance_mode == "performance":
                self.tts = StreamingXTTSClient(self.config["tts"])
                status("STREAM", "Streaming TTS engine initialized")
                status("STREAM", "Sentence-level parallel synthesis enabled")
            else:
                self.tts = XTTSClient(self.config["tts"])
                success("Standard TTS engine initialized")

            # Preload TTS model at startup to avoid delays during first synthesis
            self.tts.ensure_ready()
            success("TTS model loaded and ready.")
        except Exception as e:
            self._report_error("tts", "initialize", e)
            error(f"TTS initialization failed: {e}")

        section("[6/10] Checking standby audio files")
        self._check_and_generate_standby_clips()

        section("[6.1/10] Loading BT-7274 original voice clips")
        self._load_bt_original_clips()

        section("[6.2/10] Initializing semantic matching for BT clips")
        self._initialize_semantic_matching()

        section("[7/10] Initializing Action Handler")
        try:
            self.actions = ActionHandler(self.config["actions"])
        except Exception as e:
            self._report_error("actions", "initialize", e)
            error(f"Action handler initialization failed: {e}")

        section("[8/10] Initializing Location Services")
        try:
            manual_loc = self.config.get("location", {}).get("manual")
            self.location = LocationProvider(manual_location=manual_loc)
            if self.location.update():
                status("LOC", f"Location: {self.location.location_str}")
            else:
                warning("Location unavailable.")
        except Exception as e:
            self._report_error("location", "initialize", e)
            error(f"Location services initialization failed: {e}")

        section("[9/10] Opening persistent audio stream")
        self.recorder = PersistentAudioRecorder(self.config["stt"])
        self.recorder.start()
        success("Microphone stream active.")

        section("[10.1/10] Starting battery monitor")
        try:
            self.battery = BatteryMonitor(self.config.get("battery", {}))
            self.battery.start()
        except Exception as e:
            self._report_error("battery", "initialize", e)
            warning(f"Battery monitor failed to start: {e}")

        section("[10.2/10] Starting environmental monitor")
        try:
            self.weather = WeatherMonitor(self.config.get("environmental_warnings", {}))
            self.weather.start()
        except Exception as e:
            self._report_error("weather", "initialize", e)
            warning(f"Environmental monitor failed to start: {e}")

        section("[10.3/10] Starting VPN monitor")
        try:
            self.vpn = VPNMonitor(self.config.get("vpn", {}))
            self.vpn.start()
        except Exception as e:
            self._report_error("vpn", "initialize", e)
            warning(f"VPN monitor failed to start: {e}")

        section("[10.4/10] Initializing Protocol Brief")
        try:
            self.protocol_brief = ProtocolBrief()
            protocol_cfg = self.config.get("protocol_mode", {})
            if protocol_cfg.get("enabled", False):
                self.protocol_mode_enabled = True
                status("PROTOCOL", "Protocol Mode enabled")
                if protocol_cfg.get("auto_brief_on_start", False):
                    brief = self.protocol_brief.get_brief()
                    info("Auto protocol brief:")
                    for line in brief.split("\n"):
                        info(f"  {line}")
            else:
                status("PROTOCOL", "Protocol Mode disabled")
        except Exception as e:
            self._report_error("protocol_brief", "initialize", e)
            warning(f"Protocol Brief initialization failed: {e}")

        footer("All systems online")
        if self.performance_mode == "performance":
            status("MODE", "Performance Mode: Streaming TTS active")
        if self.protocol_mode_enabled:
            status("PROTOCOL", "Protocol Mode is active. Say 'BT, protocol brief' for a status summary.")
        info("Say 'Hey BT' or press Enter to speak.")

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
        standby_dir = Path(__file__).parent / "standby"
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
            success(f"All {total} standby clips present and loaded.")
            return

        warning(f"{len(missing)} of {total} clips missing. Generating now...")

        # Second pass: generate missing files
        generated = 0
        failed = 0
        for phrase, safe_name, key in missing:
            wav_path = standby_dir / f"{safe_name}.wav"
            info(f"[{generated + failed + 1}/{len(missing)}] Generating: {phrase}")
            try:
                if self.tts:
                    generated_wav = self.tts.speak(phrase)
                    if generated_wav:
                        import shutil
                        shutil.move(generated_wav, str(wav_path))
                        self.standby_clips[key] = str(wav_path)
                        generated += 1
                        success(f"Saved: {wav_path.name}")
                    else:
                        error(f"Failed to generate: {phrase}")
                        failed += 1
                else:
                    error(f"TTS not initialized: {phrase}")
                    failed += 1
            except Exception as e:
                error(f"Error generating '{phrase}': {e}")
                failed += 1

        success(f"Standby check complete. Loaded: {loaded}, Generated: {generated}, Failed: {failed}")

    def _load_bt_original_clips(self):
        """Load BT-7274's original voice clips from the game for instant responses."""
        import csv
        import json
        voicepack_dir = Path(__file__).parent.parent / "BT-7274.Voicepack"
        bt_clips_dir = voicepack_dir / "bt_clips"
        csv_file = voicepack_dir / "bt_clips_index.csv"
        
        # Try to load precomputed mappings first
        mappings_dir = Path(__file__).parent / "mappings"
        phrases_to_files = mappings_dir / "bt_phrases_to_files.json"
        
        if phrases_to_files.exists():
            try:
                with open(phrases_to_files, 'r') as f:
                    phrase_map = json.load(f)
                loaded = 0
                for phrase, filename in phrase_map.items():
                    wav_path = bt_clips_dir / filename
                    if wav_path.exists():
                        self.bt_clips[phrase] = str(wav_path)
                        # Extract original text from filename if needed
                        # This is a simplified approach - in practice you'd want to store the original text too
                        self.bt_clip_texts[filename] = phrase
                        loaded += 1
                success(f"Loaded {loaded} BT-7274 original voice clips from mappings.")
                return
            except Exception as e:
                warning(f"Failed to load precomputed mappings: {e}")
        
        # Fallback to loading from CSV
        if not csv_file.exists():
            warning("BT-7274 original clips CSV not found. Skipping.")
            return
            
        if not bt_clips_dir.exists():
            warning("BT-7274 original clips directory not found. Skipping.")
            return

        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                loaded = 0
                for row in reader:
                    filename = row['filename']
                    text = row['text']
                    wav_path = bt_clips_dir / filename
                    
                    if wav_path.exists():
                        # Normalize the text for matching
                        normalized_text = self._normalize_phrase(text)
                        self.bt_clips[normalized_text] = str(wav_path)
                        self.bt_clip_texts[filename] = text
                        loaded += 1
                        
                success(f"Loaded {loaded} BT-7274 original voice clips from CSV.")
        except Exception as e:
            error(f"Error loading BT-7274 original clips: {e}")

    def _initialize_semantic_matching(self):
        """Initialize semantic similarity matching for BT clips."""
        if not SEMANTIC_SIMILARITY_AVAILABLE:
            return
            
        if not self.bt_clips:
            return
            
        try:
            # Try to load cached semantic vectors first
            vectorizer_state, clip_matrix, phrases = load_semantic_vectors()
            if vectorizer_state is not None and clip_matrix is not None and phrases:
                from sklearn.feature_extraction.text import TfidfVectorizer
                self.semantic_vectorizer = TfidfVectorizer(**vectorizer_state)
                self.semantic_clip_matrix = clip_matrix
                self.semantic_clip_phrases = phrases
                success(f"Semantic similarity matching loaded from cache with {len(phrases)} phrases")
                return
            
            # Create TF-IDF vectorizer
            self.semantic_vectorizer = TfidfVectorizer(
                lowercase=True,
                stop_words='english',
                ngram_range=(1, 2),  # Use unigrams and bigrams
                max_features=1000    # Limit vocabulary size
            )
            
            # Get all phrases for semantic matching
            self.semantic_clip_phrases = list(self.bt_clips.keys())
            
            # Fit the vectorizer on all BT clip phrases
            self.semantic_clip_matrix = self.semantic_vectorizer.fit_transform(self.semantic_clip_phrases)
            
            # Persist to session cache
            vectorizer_state = {
                "lowercase": self.semantic_vectorizer.lowercase,
                "stop_words": self.semantic_vectorizer.stop_words,
                "ngram_range": self.semantic_vectorizer.ngram_range,
                "max_features": self.semantic_vectorizer.max_features,
            }
            save_semantic_vectors(vectorizer_state, self.semantic_clip_matrix, self.semantic_clip_phrases)
            
            success(f"Semantic similarity matching initialized with {len(self.semantic_clip_phrases)} phrases")
        except Exception as e:
            warning(f"Failed to initialize semantic similarity matching: {e}")
            self.semantic_vectorizer = None
            self.semantic_clip_matrix = None
            self.semantic_clip_phrases = []

    def _update_conversation_context(self, user_query: str, bot_response: str):
        """Update conversation context with the latest interaction."""
        # Add to conversation history
        self.conversation_history.append((user_query, bot_response))
        
        # Keep only the last 10 interactions to avoid memory issues
        if len(self.conversation_history) > 10:
            self.conversation_history.pop(0)
        
        # Update current context based on keywords
        user_lower = user_query.lower()
        response_lower = bot_response.lower()
        
        # Detect conversation topics
        if any(word in user_lower for word in ["weather", "temperature", "forecast"]):
            self.current_context["topic"] = "weather"
        elif any(word in user_lower for word in ["time", "date", "clock"]):
            self.current_context["topic"] = "time"
        elif any(word in user_lower for word in ["location", "where"]):
            self.current_context["topic"] = "location"
        elif any(word in user_lower for word in ["thank", "thanks", "appreciate"]):
            self.current_context["topic"] = "gratitude"
            
        # Detect emotional tone from user
        if any(word in user_lower for word in ["help", "assist", "support"]):
            self.current_context["user_emotion"] = "seeking_help"
        elif any(word in user_lower for word in ["danger", "careful", "warning"]):
            self.current_context["user_emotion"] = "concerned"
        elif any(word in user_lower for word in ["good", "great", "awesome", "perfect"]):
            self.current_context["user_emotion"] = "positive"
            
        # Detect emotional tone from bot response
        if any(word in response_lower for word in ["danger", "careful", "warning", "caution"]):
            self.current_context["bot_emotion"] = "cautious"
        elif any(word in response_lower for word in ["congratulations", "well done", "excellent"]):
            self.current_context["bot_emotion"] = "positive"
        elif any(word in response_lower for word in ["understood", "acknowledged", "copy that"]):
            self.current_context["bot_emotion"] = "neutral"

    def _get_context_aware_phrases(self) -> list[str]:
        """Get phrases that match the current conversation context."""
        context_phrases = []
        
        # Get current topic
        topic = self.current_context.get("topic", "")
        
        # Define context-specific keywords for BT clips
        context_keywords = {
            "weather": ["weather", "atmospheric", "sensors", "storm", "rain", "wind", "temperature"],
            "time": ["time", "chronometer", "clock", "date", "calendar"],
            "location": ["location", "position", "coordinates", "navigation", "map"],
            "gratitude": ["welcome", "pleasure", "assist", "help", "support"],
            "combat": ["enemy", "hostile", "titan", "weapon", "combat", "attack"],
            "mission": ["mission", "objective", "protocol", "orders", "task"],
            "status": ["status", "condition", "systems", "operational", "functional"]
        }
        
        # Get keywords for current topic
        keywords = context_keywords.get(topic, [])
        
        # Find BT clips that match these keywords
        for phrase, path in self.bt_clips.items():
            if any(keyword in phrase for keyword in keywords):
                context_phrases.append(phrase)
        
        return context_phrases

    def _detect_emotional_tone(self, text: str) -> str:
        """Detect the emotional tone of a text."""
        text_lower = text.lower()
        
        # Define emotional tone indicators
        tone_indicators = {
            "urgent": ["danger", "warning", "alert", "emergency", "critical", "hurry", "quick"],
            "cautious": ["careful", "caution", "beware", "watch out", "attention"],
            "positive": ["good", "great", "excellent", "perfect", "wonderful", "amazing"],
            "concerned": ["worry", "concern", "afraid", "scared", "nervous", "anxious"],
            "determined": ["must", "will", "shall", "determined", "committed", "resolve"],
            "neutral": ["understood", "acknowledged", "copy that", "roger", "affirmative"]
        }
        
        # Count matches for each tone
        tone_scores = {}
        for tone, indicators in tone_indicators.items():
            score = sum(1 for indicator in indicators if indicator in text_lower)
            if score > 0:
                tone_scores[tone] = score
        
        # Return the tone with highest score, or "neutral" if no matches
        if tone_scores:
            return max(tone_scores, key=tone_scores.get)
        return "neutral"

    def _get_emotion_matching_phrases(self, text: str) -> list[str]:
        """Get phrases that match the emotional tone of the text."""
        tone = self._detect_emotional_tone(text)
        
        # Define emotional tone keywords for BT clips
        emotion_keywords = {
            "urgent": ["danger", "warning", "alert", "emergency", "critical", "hurry"],
            "cautious": ["careful", "caution", "beware", "watch out", "attention"],
            "positive": ["good", "great", "excellent", "perfect", "wonderful", "congratulations"],
            "concerned": ["worry", "concern", "careful", "safe", "protect"],
            "determined": ["must", "will", "shall", "determined", "committed", "resolve", "protocol"],
            "neutral": ["understood", "acknowledged", "copy that", "roger", "affirmative", "standing by"]
        }
        
        # Get keywords for detected tone
        keywords = emotion_keywords.get(tone, [])
        
        # Find BT clips that match these emotional keywords
        matching_phrases = []
        for phrase, path in self.bt_clips.items():
            if any(keyword in phrase for keyword in keywords):
                matching_phrases.append(phrase)
        
        return matching_phrases

    def _select_dynamic_clip(self, response_text: str, context: Optional[dict] = None) -> Optional[str]:
        """Dynamically select the best BT clip based on conversation context.
        
        This method combines multiple factors to choose the most appropriate clip:
        1. Exact match priority
        2. Semantic similarity
        3. Context relevance
        4. Emotional tone matching
        5. Conversation history
        """
        if not response_text:
            return None
            
        normalized = self._normalize_phrase(response_text)
        candidates = []
        
        # 1. Exact match (highest priority)
        if normalized in self.bt_clips:
            candidates.append((self.bt_clips[normalized], 1.0, "exact"))
        
        # 2. Semantic similarity matching
        if self.semantic_vectorizer and self.semantic_clip_matrix is not None:
            try:
                response_vector = self.semantic_vectorizer.transform([normalized])
                similarities = cosine_similarity(response_vector, self.semantic_clip_matrix)
                
                # Get top 5 semantic matches
                top_indices = np.argsort(similarities[0])[-5:][::-1]
                for idx in top_indices:
                    similarity = similarities[0][idx]
                    if similarity > 0.3:
                        phrase = self.semantic_clip_phrases[idx]
                        path = self.bt_clips.get(phrase)
                        if path:
                            candidates.append((path, similarity * 0.8, "semantic"))
            except Exception as e:
                warning(f"Semantic matching failed: {e}")
        
        # 3. Context-aware matching
        context_phrases = self._get_context_aware_phrases()
        if context_phrases:
            for phrase in context_phrases:
                if normalized in phrase or phrase in normalized:
                    path = self.bt_clips.get(phrase)
                    if path:
                        candidates.append((path, 0.7, "context"))
        
        # 4. Emotional tone matching
        emotion_phrases = self._get_emotion_matching_phrases(response_text)
        if emotion_phrases:
            for phrase in emotion_phrases:
                if normalized in phrase or phrase in normalized:
                    path = self.bt_clips.get(phrase)
                    if path:
                        candidates.append((path, 0.6, "emotion"))
        
        # 5. Conversation history boost
        if self.conversation_history:
            recent_topics = set()
            for query, resp in self.conversation_history[-3:]:
                recent_topics.update(self._extract_topics(query))
            
            for phrase, path in self.bt_clips.items():
                phrase_topics = self._extract_topics(phrase)
                if recent_topics & phrase_topics:  # Intersection
                    candidates.append((path, 0.5, "history"))
        
        # Remove duplicates while keeping highest score
        seen_paths = {}
        for path, score, match_type in candidates:
            if path not in seen_paths or seen_paths[path][0] < score:
                seen_paths[path] = (score, match_type)
        
        if not seen_paths:
            return None
        
        # Select best candidate
        best_path = max(seen_paths.keys(), key=lambda p: seen_paths[p][0])
        best_score, best_type = seen_paths[best_path]
        
        # Store match info for logging
        self._last_match_type = best_type
        self._last_match_score = round(best_score, 2)
        
        info(f"Dynamic clip selected: {best_type} match (score: {best_score:.2f})")
        return best_path

    def _extract_topics(self, text: str) -> set:
        """Extract topics from text for conversation history matching."""
        text_lower = text.lower()
        topics = set()
        
        topic_keywords = {
            "combat": ["enemy", "titan", "weapon", "attack", "defend", "fight"],
            "mission": ["mission", "objective", "protocol", "orders", "task"],
            "status": ["status", "condition", "systems", "operational"],
            "location": ["location", "position", "coordinates", "navigation"],
            "pilot": ["pilot", "cooper", "jack"],
            "danger": ["danger", "warning", "alert", "emergency"],
            "support": ["help", "assist", "support", "aid"]
        }
        
        for topic, keywords in topic_keywords.items():
            if any(kw in text_lower for kw in keywords):
                topics.add(topic)
        
        return topics

    def _apply_personality_weights(self, phrases: list[str], response_text: str) -> list[tuple[str, float]]:
        """Apply personality-based weighting to phrase candidates.
        
        BT-7274's personality traits:
        - Loyal: Prioritizes pilot safety and trust
        - Formal: Military protocol and proper address
        - Tactical: Mission-focused, strategic thinking
        - Dry humor: Occasional wit, literal interpretations
        """
        weighted_phrases = []
        
        for phrase in phrases:
            weight = 1.0
            phrase_lower = phrase.lower()
            
            # Loyalty weighting - boost phrases that show pilot care
            if self.personality_weights["loyalty"] > 0.5:
                loyalty_indicators = ["pilot", "protect", "safe", "trust", "link"]
                loyalty_score = sum(1 for ind in loyalty_indicators if ind in phrase_lower)
                weight += loyalty_score * self.personality_weights["loyalty"] * 0.2
            
            # Formality weighting - boost protocol and formal language
            if self.personality_weights["formality"] > 0.5:
                formal_indicators = ["protocol", "acknowledged", "confirmed", "standing by", "copy that"]
                formal_score = sum(1 for ind in formal_indicators if ind in phrase_lower)
                weight += formal_score * self.personality_weights["formality"] * 0.15
            
            # Tactical weighting - boost mission and strategic language
            if self.personality_weights["tactical"] > 0.5:
                tactical_indicators = ["mission", "objective", "tactical", "strategic", "analyze"]
                tactical_score = sum(1 for ind in tactical_indicators if ind in phrase_lower)
                weight += tactical_score * self.personality_weights["tactical"] * 0.15
            
            # Humor weighting - boost witty or literal interpretations
            if self.personality_weights["humor"] > 0.3:
                humor_indicators = ["trust me", "i am bt", "vanguard class", "protocol 3"]
                humor_score = sum(1 for ind in humor_indicators if ind in phrase_lower)
                weight += humor_score * self.personality_weights["humor"] * 0.1
            
            # Urgency weighting - depends on detected emotion
            detected_emotion = self._detect_emotional_tone(response_text)
            if detected_emotion == "urgent" and self.personality_weights["urgency"] > 0.5:
                urgency_indicators = ["danger", "warning", "alert", "emergency", "critical"]
                urgency_score = sum(1 for ind in urgency_indicators if ind in phrase_lower)
                weight += urgency_score * self.personality_weights["urgency"] * 0.25
            
            weighted_phrases.append((phrase, weight))
        
        # Sort by weight descending
        weighted_phrases.sort(key=lambda x: x[1], reverse=True)
        return weighted_phrases

    def _update_personality_weights(self, interaction_type: str = "neutral"):
        """Update personality weights based on interaction type and trust level."""
        # Increase loyalty with more interactions
        self.personality_weights["loyalty"] = min(1.0, 0.5 + (self.pilot_trust_level * 0.1))
        
        # Adjust formality based on context
        if interaction_type == "combat":
            self.personality_weights["formality"] = 0.9
            self.personality_weights["urgency"] = 0.9
            self.personality_weights["humor"] = 0.1
        elif interaction_type == "casual":
            self.personality_weights["formality"] = 0.6
            self.personality_weights["urgency"] = 0.3
            self.personality_weights["humor"] = 0.5
        elif interaction_type == "emergency":
            self.personality_weights["formality"] = 0.95
            self.personality_weights["urgency"] = 1.0
            self.personality_weights["humor"] = 0.0
        
        # Tactical remains consistently high
        self.personality_weights["tactical"] = 0.85

    def _build_dialogue_tree(self, root_phrase: Optional[str] = None) -> dict:
        """Build an interactive dialogue tree using original game lines.
        
        Creates a tree structure where each node is a BT clip and edges
        represent logical conversation transitions.
        """
        tree = {
            "root": root_phrase or "protocol 1 link to pilot",
            "nodes": {},
            "edges": {}
        }
        
        # Define dialogue categories and their related phrases
        dialogue_categories = {
            "greeting": [
                "protocol 1 link to pilot",
                "neural link established",
                "you may call me bt",
                "i am bt7274"
            ],
            "status_check": [
                "systems operational",
                "all systems nominal",
                "standing by pilot",
                "ready to proceed"
            ],
            "mission_brief": [
                "our orders are to resume special operation 217",
                "rendezvous with major anderson of the srs",
                "the rendezvous point is 106 clicks northeast"
            ],
            "combat_ready": [
                "weapon systems online",
                "titanfall imminent",
                "engaging enemy titans",
                "defensive protocols active"
            ],
            "pilot_care": [
                "be careful pilot",
                "pilot our location has been compromised",
                "are you alright pilot",
                "i will not lose another pilot"
            ],
            "protocol_statements": [
                "protocol 1 link to pilot",
                "protocol 2 uphold the mission",
                "protocol 3 protect the pilot"
            ]
        }
        
        # Build nodes from available clips
        for category, phrases in dialogue_categories.items():
            tree["nodes"][category] = []
            for phrase in phrases:
                normalized = self._normalize_phrase(phrase)
                if normalized in self.bt_clips:
                    tree["nodes"][category].append({
                        "phrase": phrase,
                        "path": self.bt_clips[normalized],
                        "category": category
                    })
        
        # Define logical transitions between categories
        tree["edges"] = {
            "greeting": ["status_check", "mission_brief"],
            "status_check": ["mission_brief", "combat_ready", "pilot_care"],
            "mission_brief": ["combat_ready", "protocol_statements"],
            "combat_ready": ["pilot_care", "protocol_statements"],
            "pilot_care": ["protocol_statements", "status_check"],
            "protocol_statements": ["greeting", "mission_brief"]
        }
        
        return tree

    def _get_dialogue_response(self, user_input: str, current_state: str = "idle") -> Optional[str]:
        """Get the next response in a dialogue tree based on user input.
        
        Uses keyword matching to determine the most appropriate next line
        in the conversation flow.
        """
        # Build dialogue tree if not already done
        if not hasattr(self, '_dialogue_tree') or self._dialogue_tree is None:
            self._dialogue_tree = self._build_dialogue_tree()
        
        tree = self._dialogue_tree
        user_lower = user_input.lower()
        
        # Determine intent from user input
        intent = self._determine_dialogue_intent(user_input)
        
        # Get available transitions from current state
        if current_state in tree["edges"]:
            possible_categories = tree["edges"][current_state]
        else:
            possible_categories = list(tree["nodes"].keys())
        
        # Find best matching phrase based on intent
        best_match = None
        best_score = 0
        
        for category in possible_categories:
            if category not in tree["nodes"]:
                continue
                
            for node in tree["nodes"][category]:
                phrase = node["phrase"].lower()
                score = 0
                
                # Score based on intent matching
                if intent == "greeting" and category == "greeting":
                    score += 2
                elif intent == "status" and category == "status_check":
                    score += 2
                elif intent == "mission" and category == "mission_brief":
                    score += 2
                elif intent == "combat" and category == "combat_ready":
                    score += 2
                elif intent == "concern" and category == "pilot_care":
                    score += 2
                elif intent == "protocol" and category == "protocol_statements":
                    score += 2
                
                # Score based on keyword overlap
                user_words = set(user_lower.split())
                phrase_words = set(phrase.split())
                overlap = len(user_words & phrase_words)
                score += overlap
                
                if score > best_score:
                    best_score = score
                    best_match = node
        
        if best_match and best_score > 0:
            self.dialogue_state = best_match["category"]
            self.dialogue_history.append(best_match["phrase"])
            status("DIALOGUE", f"Transition: {current_state} -> {best_match['category']}")
            return best_match["path"]
        
        return None

    def _determine_dialogue_intent(self, text: str) -> str:
        """Determine the user's intent for dialogue tree navigation."""
        text_lower = text.lower()
        
        # Greeting intents
        if any(word in text_lower for word in ["hello", "hi", "hey", "greetings", "bt"]):
            return "greeting"
        
        # Status intents
        if any(word in text_lower for word in ["status", "how are you", "systems", "operational"]):
            return "status"
        
        # Mission intents
        if any(word in text_lower for word in ["mission", "objective", "orders", "task", "plan"]):
            return "mission"
        
        # Combat intents
        if any(word in text_lower for word in ["fight", "attack", "defend", "enemy", "weapon", "combat"]):
            return "combat"
        
        # Concern intents
        if any(word in text_lower for word in ["careful", "safe", "protect", "danger", "worry"]):
            return "concern"
        
        # Protocol intents
        if any(word in text_lower for word in ["protocol", "link", "trust", "protocol 1", "protocol 2", "protocol 3"]):
            return "protocol"
        
        return "general"

    def _extract_location_from_query(self, text: str) -> Optional[str]:
        """Extract location from weather query like 'weather in Tucson, Arizona'."""
        import re
        lower = text.lower()
        # Match patterns like "weather in X", "weather for X", "temperature in X"
        # Exclude common time words/phrases that shouldn't be treated as locations
        time_words = {
            "today", "tomorrow", "yesterday", "now", "tonight", "next week", "this week", 
            "next few days", "the rest of the day", "rest of the day", "rest of the week",
            "this morning", "this afternoon", "this evening", "later", "soon",
            "all day", "all week", "whole day", "whole week"
        }
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
                # Don't treat multi-word time phrases as locations
                if any(tw in location for tw in time_words):
                    return None
                # If "location" is more than 5 words, it's probably not a real location
                if len(location.split()) > 5:
                    return None
                return location
        return None

    def _is_weather_query(self, text: str) -> bool:
        """Detect if the user is asking for weather."""
        return any(kw in text.lower() for kw in ["weather", "temperature", "forecast"])

    def _is_forecast_query(self, text: str) -> bool:
        """Detect if the user is asking for a forecast (upcoming weather)."""
        lower = text.lower()
        forecast_keywords = [
            "forecast", "later today", "tomorrow", "next week", "next few days",
            "upcoming", "will it rain", "will it snow", "weekend weather",
            "this weekend", "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday", "next day", "in a few days"
        ]
        return any(kw in lower for kw in forecast_keywords)

    def _is_location_query(self, text: str) -> bool:
        """Detect if the user is asking for their location."""
        lower = text.lower().strip()
        location_phrases = ["my location", "where am i", "where are we", "find my location", "what is my location"]
        return any(kw in lower for kw in location_phrases)

    def _is_time_query(self, text: str) -> bool:
        """Detect if the user is asking for the time/date."""
        lower = text.lower().strip()
        time_keywords = ["what time", "what is the time", "current time", "what date", "what is the date", "today's date", "the date today", "what day", "what day is it"]
        return any(kw in lower for kw in time_keywords)

    def _is_status_query(self, text: str) -> bool:
        """Detect if the user is asking for BT-7274's status."""
        lower = text.lower().strip()
        status_keywords = [
            "what is your status", "what's your status", "how are you", "how are you doing",
            "status report", "systems check", "systems status", "are you operational",
            "are you online", "are you functional", "how are your systems",
            "are you okay", "are you alright", "status update", "condition report"
        ]
        return any(kw in lower for kw in status_keywords)

    def _is_vpn_status_query(self, text: str) -> bool:
        """Detect if the user is asking for VPN / cloak status."""
        lower = text.lower().strip()
        vpn_keywords = [
            "vpn status", "cloak status", "are you cloaked", "is the cloak on",
            "is the vpn on", "is vpn connected", "is proton connected",
            "vpn state", "cloak state", "network security", "are we protected",
            "is the network secure", "am i protected", "is my connection secure"
        ]
        return any(kw in lower for kw in vpn_keywords)

    def _get_status_response_clip(self) -> Optional[str]:
        """Get a BT-7274 original voice clip for status responses."""
        status_phrases = [
            "ready to proceed",
            "embark when ready",
            "please embark when ready",
            "get ready",
            "my systems are rebooting",
            "pilot my mapping systems have been restored",
            "still operational but unable to escape",
            "reinitializing critical systems",
            "standing by pilot climb onto my hand",
        ]
        import random
        # Try to find matching BT clips
        available_clips = []
        for phrase in status_phrases:
            key = self._normalize_phrase(phrase)
            if key in self.bt_clips:
                path = self.bt_clips[key]
                if Path(path).exists():
                    available_clips.append((phrase, path))

        if available_clips:
            phrase, path = random.choice(available_clips)
            clip_play(phrase, source="status")
            return path
        return None

    def _play_bt_clip_with_tts_followup(self, clip_search_text: str, tts_text: str) -> dict:
        """Play a BT original clip immediately, then follow up with TTS of the actual data.

        This provides the immersive BT-7274 voice experience while ensuring the pilot
        gets the actual information they requested.

        Returns a dict with playback info for logging:
            - clip_played: bool
            - clip_phrase: str | None
            - tts_synthesized: bool
            - tts_played: bool
        """
        import threading

        result = {
            "clip_played": False,
            "clip_phrase": None,
            "tts_synthesized": False,
            "tts_played": False,
        }

        # Find the best BT clip based on the response context
        clip_path = self._select_dynamic_clip(clip_search_text)

        if not clip_path or not Path(clip_path).exists():
            # No suitable clip found, just do TTS
            log_tts("No matching BT clip found, using TTS only...")
            wav = self.tts.speak(tts_text) if self.tts else None
            if wav:
                play_audio(wav)
                result["tts_synthesized"] = True
                result["tts_played"] = True
            return result

        # Determine clip phrase for logging
        clip_phrase = None
        for phrase, path in self.bt_clips.items():
            if path == clip_path:
                clip_phrase = phrase
                break

        if clip_phrase:
            clip_play(clip_phrase, source="BT-7274 original")
            result["clip_phrase"] = clip_phrase

        # Start TTS generation in background while the clip plays
        tts_result: list[Optional[str]] = [None]
        def generate_tts():
            try:
                if self.tts:
                    tts_result[0] = self.tts.speak(tts_text)
            except Exception as e:
                self._report_error("tts", "background_synthesis", e)

        tts_thread = threading.Thread(target=generate_tts)
        tts_thread.start()

        # Play the BT clip (blocking)
        try:
            play_audio(clip_path)
            result["clip_played"] = True
        except Exception as e:
            self._report_error("tts", "play_bt_clip", e, {"clip_path": clip_path})

        # Wait for background TTS to complete (with timeout)
        tts_thread.join(timeout=30)

        # Play the TTS follow-up
        if tts_result[0] and Path(tts_result[0]).exists():
            result["tts_synthesized"] = True
            log_tts("Playing synthesized follow-up...")
            try:
                play_audio(tts_result[0])
                result["tts_played"] = True
            except Exception as e:
                self._report_error("tts", "play_followup", e, {"tts_wav": tts_result[0]})
        else:
            warning("TTS follow-up not ready or failed.")

        return result

    def _is_search_query(self, text: str) -> bool:
        """Detect if the user is asking for real-time info that needs a web search."""
        lower = text.lower()

        # Don't treat weather queries as search queries
        if self._is_weather_query(text):
            return False

        # Don't treat VPN/cloak commands as search queries
        if self._is_vpn_toggle_command(text):
            return False

        # Don't treat todo/note commands as search queries
        if self._is_todo_command(text) or self._is_note_command(text):
            return False

        # Don't treat maintenance commands as search queries
        if self._is_maintenance_command(text):
            return False

        search_keywords = [
            "who won", "who was",
            "news", "latest",
            "search", "look up", "tell me about", "find"
        ]
        
        # Check for basic search keywords (use word boundaries to avoid false matches)
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
        # More specific travel keywords that won't match casual phrases like "go to school"
        travel_keywords = [
            "how to get", "how do i get", "travel to", "transport to",
            "route to", "directions to", "getting to", "trip to",
            "journey to", "commute to", "drive to", "fly to",
            "how do we get", "how to reach", "how can i get",
            "options to get to", "best way to get", "fastest way to get", "how do i reach",
            "how far is", "how long to get to"
        ]
        lower = text.lower()
        
        # Don't treat event information queries as travel queries
        if self._is_event_information_query(text):
            return False
        
        # Don't treat todo commands as travel queries
        if self._is_todo_command(text):
            return False
            
        return any(kw in lower for kw in travel_keywords)

    def _is_travel_query_complex(self, text: str) -> bool:
        """Detect if the user is asking about travel in a complex query."""
        lower = text.lower()
        
        # Don't treat event information queries as travel queries
        if self._is_event_information_query(text):
            return False
        
        # Don't treat todo commands as travel queries
        if self._is_todo_command(text):
            return False
        
        # Check for travel-related words combined with destinations
        travel_indicators = ["how", "way", "route", "travel", "journey"]
        has_travel_word = any(indicator in lower for indicator in travel_indicators)
        
        # Check if asking about getting somewhere specific
        getting_indicators = ["to brussels", "to antwerp", "to belgium", "getting to"]
        has_getting_phrase = any(phrase in lower for phrase in getting_indicators)
        
        return has_travel_word and has_getting_phrase

    def _mentions_destination(self, text: str) -> bool:
        """Detect if the user is mentioning getting to a specific destination."""
        # Don't treat todo commands as travel queries
        if self._is_todo_command(text):
            return False
        
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
        
        # Don't treat todo commands as travel queries
        if self._is_todo_command(text):
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

    def _is_todo_command(self, text: str) -> bool:
        """Detect if the user is giving a todo/task command."""
        lower = text.lower()
        todo_phrases = [
            "add todo", "add task", "new task", "new todo",
            "add to my to do", "add to my todo", "add to the todo",
            "put on my to do", "put on my todo", "put on the todo",
            "put on to do list", "put on todo list",
            "add to do list", "add todo list",
            "list tasks", "list todos", "show tasks", "show todos", "what are my tasks",
            "clear completed", "clear done tasks"
        ]
        return any(phrase in lower for phrase in todo_phrases)

    def _is_note_command(self, text: str) -> bool:
        """Detect if the user is giving a note command."""
        lower = text.lower()
        note_phrases = [
            "add note", "make note", "write note", "take note",
            "list notes", "show notes", "read notes", "view notes"
        ]
        return any(phrase in lower for phrase in note_phrases)

    def _is_vpn_toggle_command(self, text: str) -> bool:
        """Detect if the user is asking to turn VPN/cloak on or off."""
        lower = text.lower()
        # Turn on / enable / put on / activate
        on_phrases = [
            "turn on the vpn", "turn on vpn", "turn on cloak", "turn on the cloak",
            "enable vpn", "enable cloak", "enable the vpn", "enable the cloak",
            "put on cloak", "put on the cloak", "put on vpn", "put on the vpn",
            "activate vpn", "activate cloak", "activate the vpn", "activate the cloak",
            "start vpn", "start cloak", "start the vpn", "start the cloak",
            "engage cloak", "engage vpn", "engage the cloak", "engage the vpn",
            "cloak on", "vpn on"
        ]
        # Turn off / disable / take off / deactivate
        off_phrases = [
            "turn off the vpn", "turn off vpn", "turn off cloak", "turn off the cloak",
            "disable vpn", "disable cloak", "disable the vpn", "disable the cloak",
            "take off cloak", "take off the cloak", "take off vpn", "take off the vpn",
            "deactivate vpn", "deactivate cloak", "deactivate the vpn", "deactivate the cloak",
            "stop vpn", "stop cloak", "stop the vpn", "stop the cloak",
            "disengage cloak", "disengage vpn", "disengage the cloak", "disengage the vpn",
            "cloak off", "vpn off"
        ]
        return any(phrase in lower for phrase in on_phrases + off_phrases)

    def _is_protocol_command(self, text: str) -> bool:
        """Detect if the user is giving a protocol mode command."""
        lower = text.lower()
        protocol_phrases = [
            "protocol brief", "enable protocol mode", "turn on protocol mode",
            "activate protocol mode", "disable protocol mode", "turn off protocol mode",
            "deactivate protocol mode"
        ]
        return any(phrase in lower for phrase in protocol_phrases)

    def _is_maintenance_command(self, text: str) -> bool:
        """Detect if the user is giving a maintenance/system command."""
        lower = text.lower()
        maintenance_phrases = [
            "clear tts cache", "clear cache",
            "turn on weather warnings", "enable weather warnings",
            "turn on environmental warnings", "enable environmental warnings",
            "turn off weather warnings", "disable weather warnings",
            "turn off environmental warnings", "disable environmental warnings",
            "enable auto cloak", "turn on auto cloak", "enable auto-cloak", "turn on auto-cloak",
            "enable vpn auto connect", "turn on vpn auto connect",
            "disable auto cloak", "turn off auto cloak", "disable auto-cloak", "turn off auto-cloak",
            "disable vpn auto connect", "turn off vpn auto connect",
            "enable vpn monitor", "turn on vpn monitor", "enable cloak monitor", "turn on cloak monitor",
            "disable vpn monitor", "turn off vpn monitor", "disable cloak monitor", "turn off cloak monitor"
        ]
        return any(phrase in lower for phrase in maintenance_phrases)

    def generate_standby_responses(self, force_regenerate: bool = False):
        """Generate standby response audio files using BT's voice.
        
        Args:
            force_regenerate: If True, regenerate all clips even if they exist.
        """
        section("Generating standby responses with BT's voice")
        
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
        output_dir = Path(__file__).parent / "standby"
        output_dir.mkdir(exist_ok=True)
        
        for phrase in phrases:
            # Create safe filename
            safe_name = "".join(c if c.isalnum() or c in [' ', '-'] else "_" for c in phrase.lower())
            safe_name = safe_name.replace(" ", "_").replace("-", "_")
            output_path = output_dir / f"{safe_name}.wav"
            
            if output_path.exists() and not force_regenerate:
                info(f"Skipping: {phrase}")
                skipped_count += 1
                continue
                
            info(f"Generating: {phrase}")
            try:
                # Remove old file if forcing regeneration
                if output_path.exists() and force_regenerate:
                    output_path.unlink()
                    
                wav_path = self.tts.speak(phrase) if self.tts else None
                if wav_path:
                    import shutil
                    shutil.move(wav_path, str(output_path))
                    success(f"Saved: {output_path.name}")
                    generated_count += 1
                else:
                    error(f"Failed: {phrase}")
            except Exception as e:
                error(f"Error generating '{phrase}': {e}")
        
        footer(f"Done! Generated: {generated_count}, Skipped: {skipped_count}")
        return generated_count

    def process_command(self, audio_path: Optional[str] = None, skip_wake_word: bool = False, follow_up_depth: int = 0, pre_transcribed_text: Optional[str] = None) -> bool:
        """Process a single voice command."""
        if audio_path is None and pre_transcribed_text is None:
            raise ValueError("Either audio_path or pre_transcribed_text must be provided")

        # 1. Speech-to-Text
        stt_confidence = None
        if pre_transcribed_text is not None:
            text = pre_transcribed_text
            quote("Pilot", text)
        else:
            log_stt("Transcribing...")
            try:
                if audio_path is None:
                    raise ValueError("audio_path is required when pre_transcribed_text is not provided")
                stt_result = self.stt.transcribe(audio_path) if self.stt else {"text": "", "confidence": 0.0}
                text = stt_result.get("text", "") if isinstance(stt_result, dict) else str(stt_result)
                stt_confidence = stt_result.get("confidence") if isinstance(stt_result, dict) else None
            except Exception as e:
                self._report_error("stt", "transcribe", e, {"audio_path": audio_path})
                text = ""
                stt_confidence = 0.0
            if not text or not text.strip():
                error("No speech detected.")
                return False
            quote("Pilot", text)
            
            # Confidence-based filtering for noisy environments
            min_confidence = self.config["stt"].get("min_confidence", 0.3)
            if stt_confidence is not None and stt_confidence < min_confidence:
                warning(f"Low confidence transcription ({stt_confidence:.2f}). Treating as noise.")
                # Log rejected utterance for debugging
                try:
                    self.logger.log_interaction(
                        pilot_message=text,
                        bt_response="[REJECTED - low confidence]",
                        interaction_type="voice_rejected",
                        ai_mode=self.ai_mode,
                        performance_mode=self.performance_mode or "standard",
                        stt_confidence=stt_confidence,
                        audio_file_path=audio_path,
                        session_id=self.session_id,
                        protocol_reference="Protocol 3: Protect the Pilot",
                        pilot_trust_level=self.pilot_trust_level,
                        metadata={"rejection_reason": "low_confidence", "min_confidence": min_confidence}
                    )
                except Exception:
                    pass
                return False

        # Check wake words
        if not skip_wake_word:
            wake_words = self.config["pipeline"].get("wake_words", [])
            if wake_words and not any(ww.lower() in text.lower() for ww in wake_words):
                info("Wake word not detected. Ignoring.")
                return False

        # Helper: speak a standby phrase immediately (pre-recorded if available)
        def speak_standby(task: str = "generic"):
            task_key = f"standby_phrases_{task}"
            phrases = self.config["pipeline"].get(task_key) or self.config["pipeline"].get("standby_phrases", ["Copy that, Pilot. Stand by."])
            import random
            
            # Update personality weights based on current context
            current_topic = self.current_context.get("topic", "neutral")
            self._update_personality_weights(current_topic)
            
            # Apply personality-based weighting to phrases
            weighted_phrases = self._apply_personality_weights(phrases, " ".join(phrases))
            
            # Try context-aware phrase selection first
            context_phrases = self._get_context_aware_phrases()
            if context_phrases:
                # Filter to only phrases that are in our standby phrases and context-aware
                matching_phrases = [p for p in phrases if self._normalize_phrase(p) in context_phrases]
                if matching_phrases:
                    # Apply personality weighting to context matches
                    weighted_context = self._apply_personality_weights(matching_phrases, " ".join(matching_phrases))
                    if weighted_context:
                        phrase = weighted_context[0][0]  # Take highest weighted
                        status("STBY", f"[Context+Personality] {phrase}")
                    else:
                        phrase = random.choice(matching_phrases)
                        status("STBY", f"[Context-aware] {phrase}")
                else:
                    if weighted_phrases:
                        phrase = weighted_phrases[0][0]  # Take highest weighted
                        status("STBY", f"[Personality] {phrase}")
                    else:
                        phrase = random.choice(phrases)
                        status("STBY", phrase)
            else:
                if weighted_phrases:
                    phrase = weighted_phrases[0][0]  # Take highest weighted
                    status("STBY", f"[Personality] {phrase}")
                else:
                    phrase = random.choice(phrases)
                    status("STBY", phrase)

            # Try pre-recorded clip first (BT's original clips take priority)
            key = self._normalize_phrase(phrase)
            wav_path = self.bt_clips.get(key) or self.standby_clips.get(key)
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
            """Try to match a response to a pre-generated standby clip with enhanced matching."""
            if not response_text:
                return None
                
            normalized = self._normalize_phrase(response_text)
            
            # 1. First, try dynamic clip selection (combines all matching methods)
            dynamic_clip = self._select_dynamic_clip(response_text)
            if dynamic_clip and Path(dynamic_clip).exists():
                return dynamic_clip
            
            # 2. Check for exact BT clip match
            if normalized in self.bt_clips:
                return self.bt_clips[normalized]
            
            # 3. Check for exact standby clip match
            if normalized in self.standby_clips:
                return self.standby_clips[normalized]
                
            # 4. Try fuzzy matching for BT clips (partial matches)
            for key, path in self.bt_clips.items():
                if normalized in key or key in normalized:
                    if Path(path).exists():
                        return path
            
            # 5. Try semantic similarity matching if available
            if self.semantic_vectorizer and self.semantic_clip_matrix is not None:
                try:
                    response_vector = self.semantic_vectorizer.transform([normalized])
                    similarities = cosine_similarity(response_vector, self.semantic_clip_matrix)
                    best_match_idx = np.argmax(similarities)
                    best_similarity = similarities[0][best_match_idx]
                    
                    if best_similarity > 0.3:
                        best_phrase = self.semantic_clip_phrases[best_match_idx]
                        path = self.bt_clips.get(best_phrase)
                        if path and Path(path).exists():
                            status("MATCH", f"Semantic match: \"{best_phrase}\" (score: {best_similarity:.2f})")
                            return path
                except Exception as e:
                    warning(f"Semantic matching failed: {e}")
            
            # 6. Try context-aware phrase selection
            context_phrases = self._get_context_aware_phrases()
            if context_phrases:
                for phrase in context_phrases:
                    if normalized in phrase or phrase in normalized:
                        path = self.bt_clips.get(phrase)
                        if path and Path(path).exists():
                            status("MATCH", f"Context-aware: \"{phrase}\"")
                            return path
            
            # 7. Try emotional tone matching
            emotion_phrases = self._get_emotion_matching_phrases(response_text)
            if emotion_phrases:
                for phrase in emotion_phrases:
                    if normalized in phrase or phrase in normalized:
                        path = self.bt_clips.get(phrase)
                        if path and Path(path).exists():
                            status("MATCH", f"Emotion match: \"{phrase}\"")
                            return path
            
            # 8. Try dialogue tree navigation
            dialogue_clip = self._get_dialogue_response(response_text, self.dialogue_state)
            if dialogue_clip and Path(dialogue_clip).exists():
                return dialogue_clip
            
            # 9. Partial matches for common patterns
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
                        for key, path in self.bt_clips.items():
                            if standby_key in key and Path(path).exists():
                                return path
                        for key, path in self.standby_clips.items():
                            if standby_key in key and Path(path).exists():
                                return path
                                
            return None

        # Special handling for gratitude expressions
        # Check if gratitude is the ONLY intent (no other actionable commands)
        gratitude_only = self._is_expression_of_gratitude(text)
        if gratitude_only:
            # Check if the same utterance also contains other actionable commands
            has_other_commands = (
                self._is_vpn_toggle_command(text) or
                self._is_todo_command(text) or
                self._is_note_command(text) or
                self._is_weather_query(text) or
                self._is_time_query(text) or
                self._is_location_query(text) or
                self._is_status_query(text) or
                self._is_vpn_status_query(text) or
                self._is_search_query(text) or
                self._is_travel_query(text) or
                self._is_protocol_command(text) or
                self._is_maintenance_command(text)
            )
            if not has_other_commands:
                quote("BT-7274", "You're welcome, Pilot.")
                # Try to play pre-recorded "you're welcome" clip
                key = self._normalize_phrase("you're welcome pilot")
                # First check BT's original clips
                wav_path = self.bt_clips.get(key) or self.standby_clips.get(key)
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
                # Update conversation context
                self._update_conversation_context(text, "You're welcome, Pilot.")
                return True
            else:
                # Gratitude mixed with commands - add a gratitude response part
                # and continue processing the rest of the commands below
                response_parts.append("You're welcome, Pilot.")
                handled_types.add("gratitude")

        # 2. Handle compound queries - detect all matching query types
        response_parts = []
        handled_types = set()
        skip_normal_tts = False
        followup_tts_text = None
        lower_text = text.lower()

        # Check for location query (but not if part of longer question)
        if self._is_location_query(text):
            status("LOC", "Locating Pilot...")
            try:
                location_result = self.actions.execute("get_location") if self.actions else "Location unavailable"
                if location_result and not location_result.startswith("Location"):
                    status("LOC", location_result)
                    location_text = f"Pilot, {location_result}"
                    response_parts.append(location_text)
                    handled_types.add("location")
                    # Use BT clip + TTS followup for immersive location responses
                    skip_normal_tts = True
                    followup_tts_text = location_text
                else:
                    response_parts.append("Pilot, my navigation systems are currently unable to establish our position.")
                    handled_types.add("location")
            except Exception as e:
                self._report_error("actions", "get_location", e)
                response_parts.append("Pilot, my navigation systems are currently unable to establish our position.")
                handled_types.add("location")

        # Check for time query
        if self._is_time_query(text):
            status("TIME", "Checking chronometer...")
            try:
                time_result = self.actions.execute("tell_time") if self.actions else "Time unavailable"
                date_result = self.actions.execute("tell_date") if self.actions else "Date unavailable"
                if time_result and date_result:
                    status("TIME", time_result)
                    status("DATE", date_result)
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

        # Check for status query - respond with BT-7274 original voice clips
        if self._is_status_query(text):
            status("DIAG", "Running systems diagnostic...")
            status_clip = self._get_status_response_clip()
            if status_clip:
                try:
                    play_audio(status_clip)
                    quote("BT-7274", "[Status report via original voice clip]")
                    response_parts.append("[Status report delivered via original BT-7274 voice clip]")
                    handled_types.add("status")
                except Exception as e:
                    self._report_error("tts", "play_status_clip", e, {"status_clip": status_clip})
                    response_parts.append("Pilot, all systems are operational and ready for deployment.")
                    handled_types.add("status")
            else:
                response_parts.append("Pilot, all systems are operational and ready for deployment.")
                handled_types.add("status")

        # Check for VPN status query
        if self._is_vpn_status_query(text):
            status("VPN", "Checking cloak status...")
            if self.vpn:
                vpn_status = self.vpn.get_status()
                state = vpn_status.get("state", "unknown")
                server = vpn_status.get("server")
                wifi = vpn_status.get("wifi")
                auto_cloak = vpn_status.get("auto_cloak", False)
                if state == "connected":
                    server_str = f" via {server}" if server else ""
                    response_parts.append(f"Cloak is engaged{server_str}, Pilot. Network traffic is obfuscated.")
                else:
                    response_parts.append("Cloak is offline. We are exposed, Pilot.")
                if auto_cloak:
                    response_parts.append("Auto-cloak is enabled.")
                if wifi:
                    response_parts.append(f"Current network: {wifi}.")
            else:
                response_parts.append("VPN monitor is not initialized, Pilot.")
            handled_types.add("vpn")

        # Check for detailed cloak status command
        if any(phrase in lower_text for phrase in ["cloak status", "vpn status", "cloak details", "vpn details"]):
            status("VPN", "Retrieving cloak diagnostics...")
            if self.vpn:
                detailed_status = self.vpn.show_status()
                response_parts.append(detailed_status)
            else:
                response_parts.append("VPN monitor is not initialized, Pilot.")
            handled_types.add("vpn")

        # Check for weather query
        if self._is_weather_query(text):
            status("WEATHER", "Fetching local data...")
            try:
                # Check if user specified a location in the query
                query_location = self._extract_location_from_query(text)
                is_forecast = self._is_forecast_query(text)

                if is_forecast:
                    # Use forecast action
                    if query_location:
                        status("LOC", f"Location from query: {query_location}")
                        weather_result = self.actions.execute("get_weather_forecast", location=query_location) if self.actions else "Weather unavailable"
                    else:
                        weather_result = self.actions.execute("get_weather_forecast") if self.actions else "Weather unavailable"
                else:
                    # Use current weather action
                    if query_location:
                        status("LOC", f"Location from query: {query_location}")
                        weather_result = self.actions.execute("get_weather_for_location", location=query_location) if self.actions else "Weather unavailable"
                    else:
                        weather_result = self.actions.execute("get_weather") if self.actions else "Weather unavailable"

                if weather_result and not weather_result.startswith("Weather data unavailable") and not weather_result.startswith("Forecast data unavailable"):
                    status("WEATHER", weather_result)
                    log_llm("Summarizing for Pilot...")
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
                        # Use BT clip + TTS followup for immersive weather responses
                        skip_normal_tts = True
                        followup_tts_text = weather_response
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
            status("SEARCH", "Looking up...")
            try:
                # Enrich query with location context
                enriched_query = self.location.enrich_query(text) if self.location else text
                if enriched_query != text:
                    status("LOC", f"Localized query: {enriched_query}")
                search_result = self.actions.execute("search_web", query=enriched_query) if self.actions else "Search unavailable"
                if search_result and not search_result.startswith("Action") and not search_result.startswith("Search failed"):
                    status("SEARCH", f"Results: {search_result[:100]}...")
                    log_llm("Summarizing for Pilot...")
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
            cache_hit("Clearing TTS cache...")
            self.clear_tts_cache()
            response_parts.append("TTS cache cleared, Pilot.")
            handled_types.add("maintenance")

        # Check for environmental warnings toggle
        lower_text = text.lower()
        if any(phrase in lower_text for phrase in ["turn on weather warnings", "enable weather warnings", "turn on environmental warnings", "enable environmental warnings"]):
            if self.weather:
                self.weather.enabled = True
                self.weather.start()
                response_parts.append("Environmental warnings enabled, Pilot.")
            else:
                response_parts.append("Environmental monitor is not initialized, Pilot.")
            handled_types.add("maintenance")
        elif any(phrase in lower_text for phrase in ["turn off weather warnings", "disable weather warnings", "turn off environmental warnings", "disable environmental warnings"]):
            if self.weather:
                self.weather.enabled = False
                self.weather.stop()
                response_parts.append("Environmental warnings disabled, Pilot.")
            else:
                response_parts.append("Environmental monitor is not initialized, Pilot.")
            handled_types.add("maintenance")

        # Check for VPN / auto-cloak toggle
        if any(phrase in lower_text for phrase in ["enable auto cloak", "turn on auto cloak", "enable auto-cloak", "turn on auto-cloak", "enable vpn auto connect", "turn on vpn auto connect"]):
            if self.vpn:
                self.vpn.auto_cloak = True
                response_parts.append("Auto-cloak enabled, Pilot. I will warn you on public networks.")
            else:
                response_parts.append("VPN monitor is not initialized, Pilot.")
            handled_types.add("maintenance")
        elif any(phrase in lower_text for phrase in ["disable auto cloak", "turn off auto cloak", "disable auto-cloak", "turn off auto-cloak", "disable vpn auto connect", "turn off vpn auto connect"]):
            if self.vpn:
                self.vpn.auto_cloak = False
                response_parts.append("Auto-cloak disabled, Pilot.")
            else:
                response_parts.append("VPN monitor is not initialized, Pilot.")
            handled_types.add("maintenance")
        elif any(phrase in lower_text for phrase in ["enable vpn monitor", "turn on vpn monitor", "enable cloak monitor", "turn on cloak monitor"]):
            if self.vpn:
                self.vpn.enabled = True
                self.vpn.start()
                response_parts.append("VPN cloak monitor enabled, Pilot.")
            else:
                response_parts.append("VPN monitor is not initialized, Pilot.")
            handled_types.add("maintenance")
        elif any(phrase in lower_text for phrase in ["disable vpn monitor", "turn off vpn monitor", "disable cloak monitor", "turn off cloak monitor"]):
            if self.vpn:
                self.vpn.enabled = False
                self.vpn.stop()
                response_parts.append("VPN cloak monitor disabled, Pilot.")
            else:
                response_parts.append("VPN monitor is not initialized, Pilot.")
            handled_types.add("maintenance")

        # Check for direct VPN/cloak on/off commands
        if self._is_vpn_toggle_command(text) and "maintenance" not in handled_types:
            lower = text.lower()
            # Determine if turning on or off
            on_phrases = [
                "turn on the vpn", "turn on vpn", "turn on cloak", "turn on the cloak",
                "enable vpn", "enable cloak", "enable the vpn", "enable the cloak",
                "put on cloak", "put on the cloak", "put on vpn", "put on the vpn",
                "activate vpn", "activate cloak", "activate the vpn", "activate the cloak",
                "start vpn", "start cloak", "start the vpn", "start the cloak",
                "engage cloak", "engage vpn", "engage the cloak", "engage the vpn",
                "cloak on", "vpn on"
            ]
            off_phrases = [
                "turn off the vpn", "turn off vpn", "turn off cloak", "turn off the cloak",
                "disable vpn", "disable cloak", "disable the vpn", "disable the cloak",
                "take off cloak", "take off the cloak", "take off vpn", "take off the vpn",
                "deactivate vpn", "deactivate cloak", "deactivate the vpn", "deactivate the cloak",
                "stop vpn", "stop cloak", "stop the vpn", "stop the cloak",
                "disengage cloak", "disengage vpn", "disengage the cloak", "disengage the vpn",
                "cloak off", "vpn off"
            ]
            is_turning_on = any(phrase in lower for phrase in on_phrases)
            is_turning_off = any(phrase in lower for phrase in off_phrases)
            
            if is_turning_on:
                status("VPN", "Engaging cloak...")
                try:
                    # Try to connect VPN using the VPN monitor
                    if self.vpn:
                        result = self.vpn.connect_and_wait(timeout=15)
                        if result:
                            response_parts.append("Cloak engaged, Pilot. Network traffic is now obfuscated.")
                        else:
                            response_parts.append("Cloak connection timed out, Pilot. Check System Settings > VPN for status.")
                    else:
                        response_parts.append("VPN monitor is not initialized, Pilot.")
                except Exception as e:
                    self._report_error("vpn", "connect", e)
                    response_parts.append("Cloak engagement failed, Pilot.")
                handled_types.add("vpn")
            elif is_turning_off:
                status("VPN", "Disengaging cloak...")
                try:
                    if self.vpn:
                        result = self.vpn.disconnect()
                        if result:
                            response_parts.append("Cloak disengaged, Pilot. We are exposed.")
                        else:
                            response_parts.append("Unable to disengage cloak at this time, Pilot.")
                    else:
                        response_parts.append("VPN monitor is not initialized, Pilot.")
                except Exception as e:
                    self._report_error("vpn", "disconnect", e)
                    response_parts.append("Cloak disengagement failed, Pilot.")
                handled_types.add("vpn")

        # Check for Protocol Mode commands
        lower_text = text.lower()
        if "protocol brief" in lower_text:
            status("PROTOCOL", "Generating protocol brief...")
            try:
                if self.protocol_brief:
                    brief = self.protocol_brief.get_brief()
                    response_parts.append(brief)
                    logger.info(f"[PROTOCOL] Protocol brief generated for pilot")
                else:
                    response_parts.append("Protocol Brief system is offline, Pilot.")
                    logger.warning("[PROTOCOL] Protocol brief requested but system is offline")
            except Exception as e:
                self._report_error("protocol_brief", "get_brief", e)
                response_parts.append("Unable to generate protocol brief at this time.")
            handled_types.add("protocol")

        # Check for Protocol Mode toggle
        if any(phrase in lower_text for phrase in ["enable protocol mode", "turn on protocol mode", "activate protocol mode"]):
            self.protocol_mode_enabled = True
            response_parts.append("Protocol Mode enabled, Pilot.")
            logger.info("[PROTOCOL] Protocol Mode enabled by pilot command")
            handled_types.add("protocol")
        elif any(phrase in lower_text for phrase in ["disable protocol mode", "turn off protocol mode", "deactivate protocol mode"]):
            self.protocol_mode_enabled = False
            response_parts.append("Protocol Mode disabled, Pilot.")
            logger.info("[PROTOCOL] Protocol Mode disabled by pilot command")
            handled_types.add("protocol")

        # Check for to-do commands (using improved detection)
        if self._is_todo_command(text):
            status("PROTOCOL", "Adding to-do...")
            try:
                # Extract task text after the command phrase
                task_text = text
                # Expanded list of command phrases to strip
                todo_phrases = [
                    "add to my to do list", "add to my todo list",
                    "add to the to do list", "add to the todo list",
                    "add to do list", "add todo list",
                    "put on my to do list", "put on my todo list",
                    "put on the to do list", "put on the todo list",
                    "put on to do list", "put on todo list",
                    "add todo", "add task", "new task", "new todo"
                ]
                for phrase in todo_phrases:
                    if phrase in lower_text:
                        task_text = text[lower_text.find(phrase) + len(phrase):].strip()
                        # Strip leading punctuation
                        task_text = task_text.lstrip(",.:; ")
                        break
                if task_text:
                    if self.protocol_brief:
                        result = self.protocol_brief.add_todo(task_text)
                        response_parts.append(result)
                        logger.info(f"[PROTOCOL] To-do added: {task_text}")
                    else:
                        response_parts.append("Protocol Brief system is offline, Pilot.")
                else:
                    response_parts.append("Please specify a task to add, Pilot.")
            except Exception as e:
                self._report_error("protocol_brief", "add_todo", e)
                response_parts.append("Failed to add to-do item.")
            handled_types.add("protocol")

        if any(phrase in lower_text for phrase in ["list tasks", "list todos", "show tasks", "show todos", "what are my tasks"]):
            status("PROTOCOL", "Listing to-dos...")
            try:
                if self.protocol_brief:
                    result = self.protocol_brief.list_todo()
                    response_parts.append(result)
                    logger.info("[PROTOCOL] To-do list retrieved")
                else:
                    response_parts.append("Protocol Brief system is offline, Pilot.")
            except Exception as e:
                self._report_error("protocol_brief", "list_todo", e)
                response_parts.append("Failed to list to-do items.")
            handled_types.add("protocol")

        if any(phrase in lower_text for phrase in ["clear completed", "clear done tasks"]):
            status("PROTOCOL", "Clearing completed tasks...")
            try:
                if self.protocol_brief:
                    result = self.protocol_brief.clear_todo()
                    response_parts.append(result)
                    logger.info("[PROTOCOL] Completed to-dos cleared")
                else:
                    response_parts.append("Protocol Brief system is offline, Pilot.")
            except Exception as e:
                self._report_error("protocol_brief", "clear_todo", e)
                response_parts.append("Failed to clear completed tasks.")
            handled_types.add("protocol")

        # Check for note commands
        if any(phrase in lower_text for phrase in ["add note", "make note", "write note", "take note"]):
            status("PROTOCOL", "Adding note...")
            try:
                note_text = text
                for phrase in ["add note", "make note", "write note", "take note"]:
                    if phrase in lower_text:
                        note_text = text[lower_text.find(phrase) + len(phrase):].strip()
                        break
                if note_text:
                    if self.protocol_brief:
                        result = self.protocol_brief.add_note(note_text)
                        response_parts.append(result)
                        logger.info(f"[PROTOCOL] Note added: {note_text}")
                    else:
                        response_parts.append("Protocol Brief system is offline, Pilot.")
                else:
                    response_parts.append("Please specify note content, Pilot.")
            except Exception as e:
                self._report_error("protocol_brief", "add_note", e)
                response_parts.append("Failed to add note.")
            handled_types.add("protocol")

        if any(phrase in lower_text for phrase in ["list notes", "show notes", "read notes", "view notes"]):
            status("PROTOCOL", "Listing notes...")
            try:
                if self.protocol_brief:
                    result = self.protocol_brief.list_notes()
                    response_parts.append(result)
                    logger.info("[PROTOCOL] Notes list retrieved")
                else:
                    response_parts.append("Protocol Brief system is offline, Pilot.")
            except Exception as e:
                self._report_error("protocol_brief", "list_notes", e)
                response_parts.append("Failed to list notes.")
            handled_types.add("protocol")

        # Check for travel queries - always let LLM handle these with location context
        # But don't process travel context for event information queries (dates, prices, etc.)
        is_information_query = self._is_event_information_query(text)
        is_travel_related = (self._is_travel_query(text) or self._mentions_destination(text) or 
                           self._is_requesting_travel_options(text) or self._is_travel_query_complex(text))
        
        if is_travel_related and "travel" not in handled_types and not is_information_query:
            # For travel queries, silently get user's location and inject it into the LLM prompt
            status("LOC", "Checking your location for travel planning...")
            location_result = self.actions.execute("get_location_structured") if self.actions else "Location unavailable"
            if location_result and not location_result.startswith("Location"):
                try:
                    location_data = json.loads(location_result)
                    location_context = f"IMPORTANT PILOT LOCATION DATA - USE THIS EXACT LOCATION, DO NOT ASSUME ANY OTHER LOCATION: {location_data.get('formatted', 'Unknown')}. Coordinates: {location_data.get('coordinates', {}).get('latitude', 'N/A')}, {location_data.get('coordinates', {}).get('longitude', 'N/A')}. City: {location_data.get('city', 'Unknown')}."
                    # Add location context to the query - let LLM handle the full question
                    enriched_text = f"{text} {location_context} DO NOT MENTION GAME WORLD LOCATIONS OR FICTIONAL PLACES. USE THE PROVIDED REAL-WORLD GEOGRAPHIC INFORMATION."
                    log_llm("Thinking with location context...")
                    travel_response = self.llm.chat(enriched_text) if self.llm else "Travel information unavailable"
                    response_parts.append(travel_response)
                    handled_types.add("travel")
                except json.JSONDecodeError:
                    # Fallback to simple location if JSON parsing fails
                    simple_location = self.actions.execute("get_location") if self.actions else "Location unavailable"
                    if simple_location and not simple_location.startswith("Location"):
                        enriched_text = f"{text} IMPORTANT PILOT LOCATION DATA - USE THIS EXACT LOCATION, DO NOT ASSUME ANY OTHER LOCATION: {simple_location} DO NOT MENTION GAME WORLD LOCATIONS OR FICTIONAL PLACES. USE THE PROVIDED REAL-WORLD GEOGRAPHIC INFORMATION."
                        log_llm("Thinking with location context...")
                        travel_response = self.llm.chat(enriched_text) if self.llm else "Travel information unavailable"
                        response_parts.append(travel_response)
                        handled_types.add("travel")
                    else:
                        log_llm("Thinking...")
                        normal_response = self.llm.chat(text) if self.llm else "Response unavailable"
                        response_parts.append(normal_response)
                        handled_types.add("travel")
            else:
                log_llm("Thinking...")
                normal_response = self.llm.chat(text) if self.llm else "Response unavailable"
                response_parts.append(normal_response)
                handled_types.add("travel")
        elif is_information_query and "travel" not in handled_types and is_travel_related:
            # For event information queries, process normally without location context
            log_llm("Thinking...")
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
            log_llm("Thinking...")
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
        
        # Strip meta-text and action narration that the LLM sometimes outputs
        # Remove lines that describe actions being taken
        meta_patterns = [
            r'(?i)^\s*bt\s+(?:uses?|initiates?|performs?|executes?|triggers?|activates?|engages?|starts?)\s+.*$',
            r'(?i)^\s*bt\s+(?:is\s+)?(?:now\s+)?(?:using|initiating|performing|executing|triggering|activating|engaging|starting)\s+.*$',
            r'(?i)^\s*(?:simultaneously|meanwhile|at\s+the\s+same\s+time)\s*,?\s*bt\s+.*$',
            r'(?i)^\s*bt\s+(?:also|additionally|furthermore|moreover)\s+.*$',
            r'(?i)^\s*(?:action|system|protocol)\s*:.*$',
            r'(?i)^\s*\[.*?\]\s*bt\s+.*$',
            r'(?i)^\s*bt\s+\[.*?\]\s+.*$',
        ]
        lines = clean_response.splitlines()
        filtered_lines = []
        for line in lines:
            if not any(re.match(pattern, line) for pattern in meta_patterns):
                filtered_lines.append(line)
        clean_response = '\n'.join(filtered_lines)
        
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
                from bt7274_workstation.location import LocationProvider
                loc = LocationProvider()
                if loc.update():
                    actual_location = loc.location_str
                    clean_response = clean_response.replace("New London", actual_location)
            except:
                pass
        
        if not clean_response:
            clean_response = "Processing complete, Pilot."

        quote("BT-7274", clean_response)

        # 4. Text-to-Speech
        log_tts("Synthesizing voice...")
        output_wav = None  # Initialize to prevent unbound variable errors

        # If a handler requested clip+TTS followup (e.g. location), use that instead
        followup_result = None
        if skip_normal_tts and followup_tts_text:
            followup_result = self._play_bt_clip_with_tts_followup(followup_tts_text, followup_tts_text)
            tts_success = followup_result["tts_played"] or followup_result["clip_played"]
            standby_wav = None
            clip_source = "bt_clip" if followup_result["clip_played"] else None
            clip_phrase = followup_result["clip_phrase"]
        else:
            # Try to use a standby clip for common responses to reduce latency
            standby_wav = try_standby_for_response(clean_response)
            tts_success = False
            clip_source = None
            clip_phrase = None
            
            if standby_wav and Path(standby_wav).exists():
                # Determine if it's a BT clip or standby clip
                if standby_wav in self.bt_clips.values():
                    clip_source = "bt_clip"
                    # Find the phrase for this BT clip
                    for phrase, path in self.bt_clips.items():
                        if path == standby_wav:
                            clip_phrase = phrase
                            break
                    if clip_phrase:
                        clip_play(clip_phrase, source="BT-7274 original")
                else:
                    clip_source = "standby_clip"
                    # Find the phrase for this standby clip
                    for phrase, path in self.standby_clips.items():
                        if path == standby_wav:
                            clip_phrase = phrase
                            break
                    if clip_phrase:
                        clip_play(clip_phrase, source="standby")
                
                try:
                    play_audio(standby_wav)
                    tts_success = True
                except Exception as e:
                    self._report_error("tts", "play_standby", e, {"standby_wav": standby_wav, "clip_source": clip_source, "clip_phrase": clip_phrase})
            else:
                # Use appropriate TTS method based on performance mode
                try:
                    if self.performance_mode == "performance" and self.tts:
                        # Performance mode: Use streaming TTS for sentence-level playback
                        log_tts("Streaming TTS (sentence-level)...")
                        if self.tts and hasattr(self.tts, 'speak_streaming') and callable(getattr(self.tts, 'speak_streaming', None)):
                            try:
                                self.tts.speak_streaming(clean_response)  # type: ignore[attr-defined]
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

        # Update conversation context with the current interaction
        self._update_conversation_context(text, clean_response)

        # Log the interaction (after TTS so metrics are accurate)
        tts_metrics = getattr(self.tts, 'get_metrics', lambda: {})() if self.tts else {}
        
        # Determine cache hit type
        cache_hit_type = None
        if standby_wav and Path(standby_wav).exists():
            cache_hit_type = "standby_clip"
        elif tts_metrics and tts_metrics.get("cached"):
            cache_hit_type = "tts_cache"
        
        # Get audio file path
        audio_file_path = None
        if not (standby_wav and Path(standby_wav).exists()):
            if self.performance_mode == "performance":
                audio_file_path = "streaming"
            else:
                audio_file_path = output_wav if output_wav else None
        
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
        
        # Prepare enhanced metadata for logging
        enhanced_metadata = {
            "handled_types": list(handled_types) if 'handled_types' in locals() else [],
            "match_type": getattr(self, '_last_match_type', None),
            "match_score": getattr(self, '_last_match_score', None),
            "personality_weights": self.personality_weights.copy(),
            "dialogue_state": self.dialogue_state,
            "emotion_detected": self.current_context.get("bot_emotion", "neutral"),
            "user_emotion": self.current_context.get("user_emotion", "neutral"),
            "context_topic": self.current_context.get("topic", "general"),
            "conversation_history_length": len(self.conversation_history),
            "semantic_similarity_available": SEMANTIC_SIMILARITY_AVAILABLE,
            "clip_source": clip_source,
            "clip_phrase": clip_phrase,
            "tts_triggered": tts_success,
            "tts_synthesized": followup_result["tts_synthesized"] if followup_result else (tts_metrics.get("cached") is not None or tts_metrics.get("processing_time") is not None),
            "clip_played": followup_result["clip_played"] if followup_result else (clip_source is not None),
            "bt_running": self.running,
            "protocol_mode_enabled": self.protocol_mode_enabled,
        }
        
        self.logger.log_interaction(
            pilot_message=text,
            bt_response=clean_response,
            interaction_type="voice",
            ai_mode=self.ai_mode,
            performance_mode=self.performance_mode or "standard",
            tts_metrics=tts_metrics if tts_metrics else None,
            llm_response_time=llm_response_time if 'llm_response_time' in locals() else None,
            stt_confidence=stt_confidence,
            audio_file_path=audio_file_path,
            cache_hit=cache_hit_type,
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
            metadata=enhanced_metadata,
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

        listening("Listening for follow-up... (speak now)")
        audio_path = self.recorder.record(max_seconds=timeout) if self.recorder else record_until_silence(self.config["stt"], max_seconds=timeout)

        if not audio_path:
            return

        log_stt("Transcribing follow-up...")
        stt_result = self.stt.transcribe(audio_path) if self.stt else {"text": "", "confidence": 0.0}
        text = stt_result.get("text", "") if isinstance(stt_result, dict) else str(stt_result)

        # Clean up temp file
        try:
            os.remove(audio_path)
        except:
            pass

        if not text or not text.strip():
            error("No speech detected in follow-up.")
            return

        text = text.strip()
        quote("Pilot", text)

        # Check for gratitude expressions FIRST (before stop phrases)
        if self._is_expression_of_gratitude(text):
            quote("BT-7274", "You're welcome, Pilot.")
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
                info(f"Follow-up stopped by phrase: '{phrase}'")
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

                listening("Listening... (speak now)")
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
                    warning("Idle timeout. Unloading models to save RAM...")
                    # Optional: unload models here if memory is tight

        except KeyboardInterrupt:
            goodbye()
        finally:
            # Save session state before cleanup
            self._save_session_state()
            
            if self.recorder:
                log_system("Closing microphone stream...")
                self.recorder.stop()
            if self.battery:
                log_system("Stopping battery monitor...")
                self.battery.stop()
            if self.weather:
                log_system("Stopping environmental monitor...")
                self.weather.stop()
            self.running = False
            
            # Archive session cache and clear for next session
            log_system("Archiving session cache...")
            archive_path = archive_and_clear_session()
            if archive_path:
                success(f"Session archived to: {archive_path}")
            else:
                info("No session cache to archive.")


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
        footer(f"Successfully generated {count} standby responses!")
        return
    
    assistant.run()


if __name__ == "__main__":
    main()
