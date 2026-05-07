"""Core BT7274Assistant class: initialization, lifecycle, and main loop."""

import argparse
import json
import os
import sys
import time
import uuid
import threading
from pathlib import Path
from typing import Optional, Any

import yaml

from bt7274_assistant.pipeline._base import _AssistantBase

from bt7274_workstation.actions import ActionHandler
from bt7274_workstation.location import LocationProvider
from bt7274_workstation.interaction_logger import InteractionLogger
from bt7274_workstation.battery_monitor import BatteryMonitor
from bt7274_workstation.weather_monitor import WeatherMonitor
from bt7274_workstation.vpn_monitor import VPNMonitor
from bt7274_workstation.hardware_telemetry import HardwareTelemetry
from bt7274_workstation.network_telemetry import NetworkTelemetry
from bt7274_workstation.voice_telemetry import VoiceTelemetry
from bt7274_workstation.protocol_brief import ProtocolBrief
from bt7274_workstation.session_cache_manager import (
    save_session_state,
    archive_and_clear_session,
)
from bt7274_workstation.security_guard import SecurityGuard, PromptGuard
from bt7274_perception import PerceptionManager
from bt7274_assistant.utils import play_audio, PersistentAudioRecorder, beep, record_until_silence
from bt7274_assistant.stt import WhisperSTT
from bt7274_assistant.llm import OllamaClient, CloudLLMClient
from bt7274_assistant.tts import XTTSClient
from bt7274_assistant.tts_fast import StreamingXTTSClient
from bt7274_assistant.tts_piper import FastPiperTTS
from bt7274_assistant.ui import (
    header, section, sub_section, info, success, warning, error, status,
    bullet, spacer, divider, footer, prompt, choice_menu, box, progress, loading_bar,
    quote, log_system, log_stt, log_llm, log_tts, log_action, cache_hit,
    clip_play, listening, goodbye
)

from bt7274_assistant.pipeline.clip_matching import ClipMatchingMixin
from bt7274_assistant.pipeline.intent_detection import IntentDetectionMixin
from bt7274_assistant.pipeline.response_helpers import ResponseHelpersMixin
from bt7274_assistant.pipeline.command_processing import CommandProcessingMixin
from bt7274_assistant.translator import TranslatorTool


class BT7274Assistant(ClipMatchingMixin, IntentDetectionMixin, ResponseHelpersMixin, CommandProcessingMixin):
    """BT-7274 Voice Assistant - Main Pipeline."""

    def __init__(self, config_path: Optional[str] = None, ai_mode: str = "local", performance_mode: Optional[str] = None, console_chat_mode: bool = False, tts_engine: Optional[str] = None):
        if config_path is None:
            # core.py is in bt7274_assistant/pipeline/, config.yaml is in bt7274_assistant/
            config_path = str(Path(__file__).parent.parent / "config.yaml")
        self.config = self.load_config(config_path)
        self.ai_mode = ai_mode  # "local" or "cloud"
        self.performance_mode = performance_mode  # "standard" or "performance"
        self.console_chat_mode = console_chat_mode  # True = text input, no mic
        self.tts_engine = tts_engine  # Override for config's tts.engine (piper/xtts/vits)
        self.stt: Optional[WhisperSTT] = None
        self.llm: Optional[OllamaClient] = None
        self.tts: Optional[XTTSClient | StreamingXTTSClient | FastPiperTTS] = None
        self.actions: Optional[ActionHandler] = None
        self.location: Optional[LocationProvider] = None
        self.recorder: Optional[PersistentAudioRecorder] = None
        self.standby_clips: dict[str, str] = {}  # phrase -> wav_path
        self._standby_shortlist: list[str] = []  # Pre-computed standby clip paths
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
        self.hardware_telemetry: Optional[HardwareTelemetry] = None
        self.network_telemetry: Optional[NetworkTelemetry] = None
        self.voice_telemetry: Optional[VoiceTelemetry] = None
        self.perception: Optional[PerceptionManager] = None
        self.vision_viewer = None  # VisionViewerWindow instance (lazy-init)
        self._hud_window = None    # CameraWindow instance for Pilot HUD
        
        # Protocol reference cooldown to prevent spam
        self._last_protocol_reference: Optional[str] = None
        self._protocol_cooldown_until: float = 0.0
        self._protocol_cooldown_seconds: float = 30.0  # Minimum seconds between same protocol reference
        
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
        
        # Task focus management
        self.focused_task = False       # Flag to indicate when BT is focusing on a task
        self.task_lock = threading.Lock()  # Lock for thread-safe task management

        # Autonomous logging state
        self.autonomous_log_cooldown_until: float = 0.0
        self.autonomous_logs_this_session: int = 0
        self.autonomous_log_max_per_session: int = self.config.get("llm", {}).get("autonomous_logging", {}).get("max_per_session", 30)
        self.autonomous_log_enabled: bool = self.config.get("llm", {}).get("autonomous_logging", {}).get("enabled", True)
        self.autonomous_log_cooldown_seconds: float = self.config.get("llm", {}).get("autonomous_logging", {}).get("cooldown_seconds", 60)
        self._last_autonomous_log_hash: str = ""  # Deduplication hash

        # Security
        security_config = self.config.get("security", {})
        self.security_enabled = security_config.get("enabled", True)
        if self.security_enabled:
            self.security_guard = SecurityGuard(
                allow_http_hosts=set(security_config.get("allow_http_hosts", ["ip-api.com"])),
                max_calls_per_minute=security_config.get("rate_limits", {}),
            )
            self.prompt_guard = PromptGuard()
        else:
            self.security_guard = None
            self.prompt_guard = None

        # Translator tool
        self.translator: Optional[TranslatorTool] = None

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
        error_entry: dict[str, Any] = {
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

    def _process_command_async(self, audio_path: str):
        """Process a command asynchronously to keep the microphone always listening."""
        def process_thread():
            try:
                # Set task focus flag
                with self.task_lock:
                    self.focused_task = True
                
                # Process the command
                self.process_command(audio_path)
                
                # Clean up temp file
                try:
                    os.remove(audio_path)
                except:
                    pass
                    
            except Exception as e:
                self._report_error("pipeline", "process_command_async", e)
                error(f"Error in async command processing: {e}")
            finally:
                # Release task focus flag
                with self.task_lock:
                    self.focused_task = False
        
        # Start processing in a separate thread with limited concurrency
        # Limit to 3 concurrent threads to prevent resource exhaustion
        if len([t for t in self.active_threads if t.is_alive()]) < 3:
            thread = threading.Thread(target=process_thread, daemon=True)
            thread.start()
            self.active_threads.append(thread)
            return thread
        else:
            # If too many threads are running, process synchronously to avoid overload
            warning("Too many concurrent tasks, processing synchronously")
            try:
                self.process_command(audio_path)
                try:
                    os.remove(audio_path)
                except:
                    pass
            except Exception as e:
                self._report_error("pipeline", "process_command_sync", e)
                error(f"Error in sync command processing: {e}")
            return None

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
                "console_chat_mode": self.console_chat_mode,
            }
            save_session_state(state)
        except Exception as e:
            warning(f"Failed to save session state: {e}")

    def load_config(self, path: str) -> dict:
        with open(path, 'r') as f:
            return yaml.safe_load(f)

    def _ensure_log_directories(self):
        """Ensure all required log directories exist at startup via centralized manager."""
        from bt7274_workstation.log_manager import (
            get_conversations_dir,
            get_bt_memory_dir,
            get_pilot_memory_dir,
            get_telemetry_system_dir,
            get_telemetry_health_dir,
            get_telemetry_voice_dir,
            get_telemetry_hardware_dir,
            get_telemetry_network_dir,
            get_vision_dir,
            get_archive_dir,
            migrate_legacy_logs,
        )
        # Ensure new hierarchy exists
        _ = get_conversations_dir()
        _ = get_bt_memory_dir()
        _ = get_pilot_memory_dir()
        _ = get_telemetry_system_dir()
        _ = get_telemetry_health_dir()
        _ = get_telemetry_voice_dir()
        _ = get_telemetry_hardware_dir()
        _ = get_telemetry_network_dir()
        _ = get_vision_dir()
        _ = get_archive_dir()
        # One-shot migration of old flat layout
        migrate_legacy_logs()

    def initialize(self):
        """Initialize all components."""
        header("BT-7274 AI ASSISTANT  |  Protocol 1: Link to Pilot")

        if self.console_chat_mode:
            info("Console Chat Mode — Text input only")
            spacer()

        # Pre-init: LLM selection (moved above system init)
        if self.ai_mode is None:
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
            mode_name = "Local" if self.ai_mode == "local" else "Cloud"
            model_name = self.config["llm"][self.ai_mode]["model"]
            status("USING", f"{mode_name} Ollama ({model_name})")

        # Pre-init: Performance mode selection (moved above system init)
        if self.performance_mode is None:
            info("[1] Standard — Full synthesis, then play")
            info("[2] Streaming — Sentence-level parallel playback")
            while True:
                try:
                    choice = prompt("Select mode [1-2]:")
                    if choice == "1":
                        self.performance_mode = "standard"
                        status("SELECT", "Standard")
                        break
                    elif choice == "2":
                        self.performance_mode = "performance"
                        status("SELECT", "Streaming")
                        break
                    else:
                        warning("Invalid choice. Please enter 1 or 2.")
                except (EOFError, KeyboardInterrupt):
                    info("Exiting...")
                    sys.exit(0)
        else:
            mode_display = "Standard" if self.performance_mode == "standard" else "Streaming"
            status("USING", f"{mode_display} (preselected)")

        spacer()
        section("Initializing Systems")

        # [0] Log directories
        self._ensure_log_directories()
        success("Log directories")

        # Initialize encryption key if needed
        if self.config.get("security", {}).get("encrypt_sensitive_logs", True):
            from bt7274_workstation.log_manager import ensure_encryption_key
            if ensure_encryption_key():
                info("Generated new encryption key for sensitive log data.")

        # [1] Speech-to-Text
        if not self.console_chat_mode:
            try:
                self.stt = WhisperSTT(self.config["stt"])
                _ = self.stt.model
                success("Speech-to-Text")
            except Exception as e:
                self._report_error("stt", "initialize", e)
                warning("Speech-to-Text failed")
        else:
            info("Speech-to-Text — skipped (chat mode)")

        # [2] LLM
        try:
            llm_config = self.config["llm"][self.ai_mode].copy()
            llm_config["system_prompt"] = self.config["llm"].get("system_prompt", "")
            self.llm = OllamaClient(llm_config)
            success("LLM")
        except Exception as e:
            self._report_error("llm", "initialize", e)
            error("LLM failed")

        # [3] Text-to-Speech
        try:
            tts_engine = self.tts_engine or self.config.get("tts", {}).get("engine", "xtts")
            
            if tts_engine == "piper":
                piper_tts = FastPiperTTS(self.config["tts"])
                if piper_tts._is_ready():
                    self.tts = piper_tts
                    status("TTS", "Piper engine (sub-second)")
                else:
                    warning("Piper not available, falling back to VITS")
                    tts_engine = "vits"
            
            if tts_engine == "vits":
                self.tts = XTTSClient(self.config["tts"])
                self.tts.model_name = "tts_models/en/ljspeech/vits"
                status("TTS", "VITS engine (fast)")
            elif tts_engine == "xtts":
                if self.performance_mode == "performance":
                    self.tts = StreamingXTTSClient(self.config["tts"])
                    status("STREAM", "Streaming XTTS initialized")
                else:
                    self.tts = XTTSClient(self.config["tts"])
                    status("TTS", "XTTS v2 engine (authentic BT voice)")
            
            self.tts.ensure_ready()
            success("TTS ready")
        except Exception as e:
            self._report_error("tts", "initialize", e)
            error("TTS failed")

        # [4] Standby clips
        self._check_and_generate_standby_clips()

        # [5] BT original clips + semantic matching
        self._load_bt_original_clips()
        # Semantic matching index is lazy-loaded on first use

        # [6] Action Handler
        try:
            self.actions = ActionHandler(self.config["actions"])
            success("Action Handler")
        except Exception as e:
            self._report_error("actions", "initialize", e)
            warning("Action Handler failed")

        # [7] Location
        try:
            manual_loc = self.config.get("location", {}).get("manual")
            self.location = LocationProvider(manual_location=manual_loc)
            if self.location.update():
                status("LOC", self.location.location_str)
            else:
                warning("Location unavailable")
        except Exception as e:
            self._report_error("location", "initialize", e)
            warning("Location failed")

        # [8] Audio Stream
        if not self.console_chat_mode:
            self.recorder = PersistentAudioRecorder(self.config["stt"])
            self.recorder.start()
            success("Audio stream active")
        else:
            info("Audio stream — skipped (chat mode)")

        # [9] Monitors
        try:
            self.battery = BatteryMonitor(self.config.get("battery", {}))
            self.battery.start()
            success("Battery monitor")
        except Exception as e:
            self._report_error("battery", "initialize", e)
            warning("Battery monitor failed")

        try:
            self.weather = WeatherMonitor(self.config.get("environmental_warnings", {}))
            self.weather.start()
            success("Environmental monitor")
        except Exception as e:
            self._report_error("weather", "initialize", e)
            warning("Environmental monitor failed")

        try:
            self.vpn = VPNMonitor(self.config.get("vpn", {}))
            self.vpn.start()
            success("VPN monitor")
        except Exception as e:
            self._report_error("vpn", "initialize", e)
            warning("VPN monitor failed")

        # [9b] Telemetry monitors
        try:
            self.hardware_telemetry = HardwareTelemetry(self.config.get("hardware_telemetry", {}))
            self.hardware_telemetry.start()
            success("Hardware telemetry")
        except Exception as e:
            self._report_error("hardware_telemetry", "initialize", e)
            warning("Hardware telemetry failed")

        try:
            self.network_telemetry = NetworkTelemetry(self.config.get("network_telemetry", {}))
            self.network_telemetry.start()
            success("Network telemetry")
        except Exception as e:
            self._report_error("network_telemetry", "initialize", e)
            warning("Network telemetry failed")

        try:
            self.voice_telemetry = VoiceTelemetry(self.config.get("voice_telemetry", {}))
            success("Voice telemetry")
        except Exception as e:
            self._report_error("voice_telemetry", "initialize", e)
            warning("Voice telemetry failed")

        # [10] Perception (Camera Vision)
        try:
            vision_cfg = self.config.get("vision", {})
            if vision_cfg.get("enabled", True):
                self.perception = PerceptionManager(
                    camera_device=vision_cfg.get("camera_device", "0"),
                    ollama_url=vision_cfg.get("ollama_url", "http://localhost:11434"),
                    vision_model=vision_cfg.get("vision_model", "llava"),
                )
                if self.perception.is_ready():
                    success("Optical sensors online")
                else:
                    status("VISION", "Optical sensors standby (install a vision model: ollama pull llava)")
            else:
                info("Vision — disabled in config")
        except Exception as e:
            self._report_error("perception", "initialize", e)
            warning("Optical sensors failed")

        # [11] Protocol Brief
        try:
            self.protocol_brief = ProtocolBrief()
            protocol_cfg = self.config.get("protocol_mode", {})
            if protocol_cfg.get("enabled", False):
                self.protocol_mode_enabled = True
                status("PROTOCOL", "Enabled")
                if protocol_cfg.get("auto_brief_on_start", False):
                    brief = self.protocol_brief.get_brief()
                    for line in brief.split("\n"):
                        info(f"  {line}")
            else:
                status("PROTOCOL", "Disabled")
        except Exception as e:
            self._report_error("protocol_brief", "initialize", e)
            warning("Protocol Brief failed")

        # [11] Translator
        try:
            self.translator = TranslatorTool(llm_client=self.llm)
            status("TRANSLATE", "Ready")
        except Exception as e:
            self._report_error("translator", "initialize", e)
            warning("Translator failed")

        divider()
        footer("All systems online")
        if self.console_chat_mode:
            status("MODE", "Console Chat — Type your messages below")
            log_system("Session started in console chat mode")
        elif self.performance_mode == "performance":
            status("MODE", "Performance Mode — Streaming TTS active")
            log_system("Session started in voice mode (performance)")
        else:
            log_system("Session started in voice mode (standard)")
        if self.protocol_mode_enabled:
            status("PROTOCOL", "Say 'BT, protocol brief' for a status summary")
        if not self.console_chat_mode:
            info("Say 'Hey BT' or press Enter to speak")

    def _check_and_generate_standby_clips(self):
        """Check all standby phrases from config and generate missing .wav files.

        Phrases are organized into category subfolders under standby/:
          generic/, weather/, search/, location/, time/, translate/
        Missing clips are generated into their respective subfolder.
        """
        standby_dir = Path(__file__).parent.parent / "standby"
        standby_dir.mkdir(exist_ok=True)

        # Map each standby_phrases_* key to its subfolder
        CATEGORY_MAP = {
            "standby_phrases": "generic",
            "standby_phrases_weather": "weather",
            "standby_phrases_search": "search",
            "standby_phrases_location": "location",
            "standby_phrases_time": "time",
            "standby_phrases_translate": "translate",
        }

        # Collect phrases grouped by category
        pipeline = self.config.get("pipeline", {})
        phrases_by_category: dict[str, list[str]] = {}
        for key, subfolder in CATEGORY_MAP.items():
            if key in pipeline:
                phrases_by_category.setdefault(subfolder, []).extend(pipeline[key])

        # Flatten for deduplication while preserving category for the first occurrence
        seen = set()
        phrase_to_category: dict[str, str] = {}
        for subfolder, phrases in phrases_by_category.items():
            for p in phrases:
                if p not in seen:
                    seen.add(p)
                    phrase_to_category[p] = subfolder

        # First pass: check which files exist (search category subfolder, then fallback recursive)
        missing = []
        loaded = 0
        for phrase, subfolder in phrase_to_category.items():
            safe_name = "".join(c if c.isalnum() or c in [' ', '-'] else "_" for c in phrase.lower())
            safe_name = safe_name.replace(" ", "_").replace("-", "_")
            key = self._normalize_phrase(phrase)

            # 1. Check the correct category subfolder first
            category_dir = standby_dir / subfolder
            category_dir.mkdir(exist_ok=True)
            category_path = category_dir / f"{safe_name}.wav"
            if category_path.exists():
                self.standby_clips[key] = str(category_path)
                loaded += 1
                continue

            # 2. Fallback: search recursively anywhere in standby/
            found_paths = list(standby_dir.rglob(f"{safe_name}.wav"))
            if found_paths:
                self.standby_clips[key] = str(found_paths[0])
                loaded += 1
            else:
                missing.append((phrase, safe_name, key, subfolder))

        # Report status
        total = len(phrase_to_category)
        if not missing:
            success(f"All {total} standby clips present and loaded.")
            return

        warning(f"{len(missing)} of {total} clips missing. Generating now...")

        # Second pass: generate missing files into their category subfolder
        generated = 0
        failed = 0
        total_missing = len(missing)
        for i, (phrase, safe_name, key, subfolder) in enumerate(missing):
            loading_bar("Generating standby clips", i, total_missing)
            category_dir = standby_dir / subfolder
            category_dir.mkdir(exist_ok=True)
            wav_path = category_dir / f"{safe_name}.wav"
            try:
                if self.tts:
                    generated_wav = self.tts.speak(phrase)
                    if generated_wav:
                        import shutil
                        shutil.move(generated_wav, str(wav_path))
                        self.standby_clips[key] = str(wav_path)
                        generated += 1
                    else:
                        error(f"Failed to generate: {phrase}")
                        failed += 1
                else:
                    error(f"TTS not initialized: {phrase}")
                    failed += 1
            except Exception as e:
                error(f"Error generating '{phrase}': {e}")
                failed += 1
        loading_bar("Generating standby clips", total_missing, total_missing)

        success(f"Standby check complete. Loaded: {loaded}, Generated: {generated}, Failed: {failed}")

        # Pre-compute a shortlist of available standby clips for instant playback
        standby_phrases = self.config.get("pipeline", {}).get("standby_phrases", [])
        self._standby_shortlist = []
        for phrase in standby_phrases:
            key = self._normalize_phrase(phrase)
            path = self.standby_clips.get(key)
            if path and Path(path).exists():
                self._standby_shortlist.append(path)
        if not self._standby_shortlist:
            # Fallback: grab any available standby clip
            self._standby_shortlist = [p for p in self.standby_clips.values() if Path(p).exists()]

    def run(self):
        """Main interaction loop."""
        self.initialize()
        self.running = True
        self.focused_task = False  # Flag to indicate when BT is focusing on a task
        self.active_threads = []   # Track active processing threads
        self.last_cleanup_time = time.time()  # For periodic cleanup

        if self.console_chat_mode:
            self._run_console_chat()
        else:
            self._run_voice_mode()

    def _run_console_chat(self):
        """Console chat mode — text input like a local ollama terminal chat."""
        try:
            while self.running:
                try:
                    # Prompt looks like: > BT, where are we?
                    user_input = input("\n  > ")
                except (EOFError, KeyboardInterrupt):
                    goodbye()
                    break

                if not user_input or not user_input.strip():
                    continue

                user_input = user_input.strip()

                # Exit commands
                lower = user_input.lower()
                if lower in ("exit", "quit", "bye", "goodbye", "shutdown"):
                    quote("BT-7274", "Goodbye, Pilot.")
                    break

                # Update activity timestamp
                self.last_activity = time.time()
                self.interaction_count += 1
                self.errors_this_interaction = []

                # Process the text command directly (skip wake word, skip STT)
                self.process_command(
                    audio_path=None,
                    skip_wake_word=True,
                    pre_transcribed_text=user_input
                )

        except KeyboardInterrupt:
            goodbye()
        finally:
            self._shutdown()

    def _run_voice_mode(self):
        """Voice mode — continuous microphone listening."""
        try:
            # Start continuous listening
            if self.recorder:
                self.recorder.start()

            while self.running:
                # Periodic cleanup of finished threads (every 5 seconds) to prevent memory leaks
                current_time = time.time()
                if current_time - self.last_cleanup_time > 5.0:
                    self.active_threads = [t for t in self.active_threads if t.is_alive()]
                    self.last_cleanup_time = current_time

                # Always keep listening unless focusing on a task
                if not self.focused_task and self.recorder:
                    # Check if audio is ready to be processed
                    if self.recorder.is_audio_ready():
                        # Get the ready audio without blocking
                        audio_path = self.recorder.get_ready_audio()
                        if audio_path:
                            # Process command asynchronously to keep listening
                            self._process_command_async(audio_path)

                    # Adaptive delay based on system load
                    # Shorter delay when threads are active for better responsiveness
                    active_thread_count = len([t for t in self.active_threads if t.is_alive()])
                    if active_thread_count > 0:
                        time.sleep(0.005)  # 5ms when processing tasks
                    else:
                        time.sleep(0.01)   # 10ms when idle
                else:
                    # When focusing on a task, wait a bit before checking again
                    time.sleep(0.02)  # 20ms when focused on task

                # Idle timeout check (reduced frequency to save CPU)
                if current_time - self.last_activity > 60:  # Check every minute
                    idle_timeout = self.config["pipeline"].get("idle_timeout", 300)
                    if current_time - self.last_activity > idle_timeout:
                        warning("Idle timeout. Unloading models to save RAM...")
                        # Optional: unload models here if memory is tight
                        self.last_activity = current_time  # Reset timer to prevent repeated warnings

        except KeyboardInterrupt:
            goodbye()
        finally:
            self._shutdown()

    def _shutdown(self):
        """Clean shutdown sequence."""
        # Wait for all processing threads to complete before shutting down (with timeout)
        alive_threads = [t for t in self.active_threads if t.is_alive()]
        if alive_threads:
            info(f"Waiting for {len(alive_threads)} processing tasks to complete...")
            for thread in alive_threads:
                thread.join(timeout=1.0)  # Wait up to 1 second for each thread

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
        if self.hardware_telemetry:
            log_system("Stopping hardware telemetry...")
            self.hardware_telemetry.stop()
        if self.network_telemetry:
            log_system("Stopping network telemetry...")
            self.network_telemetry.stop()
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
    parser.add_argument("--console-chat-mode", action="store_true",
                        help="Run in console chat mode (text input, no microphone)")
    args = parser.parse_args()

    # Initialize with no preset modes so user can choose during startup
    assistant = BT7274Assistant(
        ai_mode=args.ai_mode,
        performance_mode=args.performance_mode,
        console_chat_mode=args.console_chat_mode,
    )

    if args.generate_responses or args.force_regenerate:
        # Initialize all components first
        assistant.initialize()
        count = assistant.generate_standby_responses(force_regenerate=args.force_regenerate)
        footer(f"Successfully generated {count} standby responses!")
        return

    assistant.run()


if __name__ == "__main__":
    main()

