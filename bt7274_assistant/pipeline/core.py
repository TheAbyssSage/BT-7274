"""Core BT7274Assistant class: initialization, lifecycle, and main loop."""

import argparse
import json
import os
import sys
import time
import uuid
import threading
from pathlib import Path
from typing import Optional

import yaml

from bt7274_workstation.actions import ActionHandler
from bt7274_workstation.location import LocationProvider
from bt7274_workstation.interaction_logger import InteractionLogger
from bt7274_workstation.battery_monitor import BatteryMonitor
from bt7274_workstation.weather_monitor import WeatherMonitor
from bt7274_workstation.vpn_monitor import VPNMonitor
from bt7274_workstation.protocol_brief import ProtocolBrief
from bt7274_workstation.session_cache_manager import (
    save_session_state,
    archive_and_clear_session,
)
from utils import play_audio, PersistentAudioRecorder, beep, record_until_silence
from stt import WhisperSTT
from llm import OllamaClient, CloudLLMClient
from tts import XTTSClient
from tts_fast import StreamingXTTSClient
from ui import (
    header, section, sub_section, info, success, warning, error, status,
    bullet, spacer, divider, footer, prompt, choice_menu, box, progress,
    quote, log_system, log_stt, log_llm, log_tts, log_action, cache_hit,
    clip_play, listening, goodbye
)

from bt7274_assistant.pipeline.clip_matching import ClipMatchingMixin
from bt7274_assistant.pipeline.intent_detection import IntentDetectionMixin
from bt7274_assistant.pipeline.response_helpers import ResponseHelpersMixin
from bt7274_assistant.pipeline.command_processing import CommandProcessingMixin


class BT7274Assistant(ClipMatchingMixin, IntentDetectionMixin, ResponseHelpersMixin, CommandProcessingMixin):
    """BT-7274 Voice Assistant - Main Pipeline."""

    def __init__(self, config_path: Optional[str] = None, ai_mode: str = "local", performance_mode: Optional[str] = None):
        if config_path is None:
            # core.py is in bt7274_assistant/pipeline/, config.yaml is in bt7274_assistant/
            config_path = str(Path(__file__).parent.parent / "config.yaml")
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

        # First pass: check which files exist (search recursively in subfolders)
        missing = []
        loaded = 0
        for phrase in unique_phrases:
            safe_name = "".join(c if c.isalnum() or c in [' ', '-'] else "_" for c in phrase.lower())
            safe_name = safe_name.replace(" ", "_").replace("-", "_")
            key = self._normalize_phrase(phrase)

            # Search recursively in standby_dir for the file
            found_paths = list(standby_dir.rglob(f"{safe_name}.wav"))
            if found_paths:
                wav_path = found_paths[0]
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

    def run(self):
        """Main voice interaction loop."""
        self.initialize()
        self.running = True
        self.focused_task = False  # Flag to indicate when BT is focusing on a task
        self.active_threads = []   # Track active processing threads
        self.last_cleanup_time = time.time()  # For periodic cleanup

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

