#!/usr/bin/env python3
"""
Integration test for BT-7274 command handlers.
Tests the actual command routing logic without loading heavy models.
"""

import sys
import os
import re
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

# We need to mock heavy imports before importing pipeline
mock_modules = {
    'whisper': MagicMock(),
    'TTS': MagicMock(),
    'TTS.api': MagicMock(),
    'torch': MagicMock(),
    'sounddevice': MagicMock(),
    'soundfile': MagicMock(),
    'numpy': MagicMock(),
    'scipy': MagicMock(),
    'scipy.signal': MagicMock(),
    'sklearn': MagicMock(),
    'sklearn.feature_extraction': MagicMock(),
    'sklearn.metrics': MagicMock(),
}

for name, mod in mock_modules.items():
    sys.modules[name] = mod

# Now import pipeline
from bt7274.bt7274_assistant.pipeline import BT7274Assistant


class CommandRouterTester:
    """Test command routing without initializing heavy models."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.assistant = None
        self._setup_assistant()

    def _setup_assistant(self):
        """Create a minimal assistant with mocked dependencies."""
        # Create a minimal config
        config = {
            "stt": {
                "model": "base.en",
                "language": "en",
                "device": "cpu",
                "sample_rate": 16000,
                "silence_threshold": 0.015,
                "silence_duration": 2.5,
                "max_record_seconds": 15,
                "post_wake_grace": 1.5,
                "min_confidence": 0.3
            },
            "llm": {
                "local": {"model": "bt7274", "url": "http://localhost:11434", "temperature": 0.7, "max_tokens": 200},
                "cloud": {"model": "gpt-oss:120b-cloud", "url": "http://localhost:11434", "temperature": 0.7, "max_tokens": 300},
                "system_prompt": "You are BT-7274."
            },
            "tts": {
                "model": "tts_models/multilingual/multi-dataset/xtts_v2",
                "reference_wav": "bt7274_assistant/dataset/reference_speaker.wav",
                "language": "en",
                "speed": 1.0,
                "output_dir": "bt7274_workstation/session_cache/tts_outputs",
                "use_mps": False
            },
            "pipeline": {
                "wake_words": ["bt", "hey bt"],
                "standby_phrases": ["Copy that, Pilot. Stand by."],
                "follow_up": {"max_depth": 1, "timeout_seconds": 8, "stop_phrases": ["no", "never mind", "stop"]},
                "idle_timeout": 300
            },
            "actions": {"enabled": True, "allowed_commands": ["say", "open", "run_script", "set_volume", "tell_time", "tell_date", "web_search", "trigger_shortcut", "search_web", "get_location", "get_location_structured", "get_weather", "get_weather_for_location", "get_weather_forecast", "clear_tts_cache", "read_logs", "make_log", "read_bt_logs", "protocol_brief"]},
            "location": {},
            "battery": {"enabled": True, "interval": 60, "thresholds": [50, 20, 10, 5]},
            "environmental_warnings": {"enabled": True, "interval": 300},
            "vpn": {"enabled": True, "interval": 10, "provider": "protonvpn"},
            "protocol_mode": {"enabled": False, "auto_brief_on_start": False}
        }

        # Create assistant without calling initialize()
        self.assistant = BT7274Assistant.__new__(BT7274Assistant)
        self.assistant.config = config
        self.assistant.ai_mode = "local"
        self.assistant.performance_mode = "standard"
        self.assistant.stt = None
        self.assistant.llm = None
        self.assistant.tts = None
        self.assistant.actions = None
        self.assistant.location = None
        self.assistant.recorder = None
        self.assistant.standby_clips = {}
        self.assistant.bt_clips = {}
        self.assistant.bt_clip_texts = {}
        self.assistant.running = False
        self.assistant.last_activity = 0
        self.assistant.logger = MagicMock()
        self.assistant.session_id = "test_session"
        self.assistant.session_start_time = 0
        self.assistant.interaction_count = 0
        self.assistant.pilot_trust_level = 1
        self.assistant.errors_this_session = []
        self.assistant.errors_this_interaction = []
        self.assistant.actions_this_session = []
        self.assistant.weather_context = None
        self.assistant.battery = None
        self.assistant.weather = None
        self.assistant.vpn = None
        self.assistant.protocol_mode_enabled = False
        self.assistant.protocol_brief = None
        self.assistant.semantic_vectorizer = None
        self.assistant.semantic_clip_matrix = None
        self.assistant.semantic_clip_phrases = []
        self.assistant.conversation_history = []
        self.assistant.current_context = {}
        self.assistant.personality_weights = {"loyalty": 1.0, "formality": 0.8, "tactical": 0.9, "humor": 0.3, "urgency": 0.5}
        self.assistant.dialogue_state = "idle"
        self.assistant.dialogue_history = []
        self.assistant.available_transitions = {}

    def test(self, name: str, condition: bool):
        if condition:
            print(f"  ✅ PASS: {name}")
            self.passed += 1
        else:
            print(f"  ❌ FAIL: {name}")
            self.failed += 1

    def run_all_tests(self):
        print("=" * 60)
        print("BT-7274 Command Router Integration Tests")
        print("=" * 60)

        a = self.assistant

        # ─── Todo Commands ───
        print("\n📋 Todo Command Routing")
        self.test("'add todo buy milk' -> _is_todo_command", a._is_todo_command("add todo buy milk"))
        self.test("'add to my to do list go home' -> _is_todo_command", a._is_todo_command("add to my to do list go home"))
        self.test("'put on my todo list call mom' -> _is_todo_command", a._is_todo_command("put on my todo list call mom"))
        self.test("'list tasks' -> _is_todo_command", a._is_todo_command("list tasks"))
        self.test("'clear completed' -> _is_todo_command", a._is_todo_command("clear completed"))
        self.test("'what is the weather' NOT todo", not a._is_todo_command("what is the weather"))

        # ─── Note Commands ───
        print("\n📝 Note Command Routing")
        self.test("'add note remember this' -> _is_note_command", a._is_note_command("add note remember this"))
        self.test("'list notes' -> _is_note_command", a._is_note_command("list notes"))
        self.test("'add todo' NOT note", not a._is_note_command("add todo"))

        # ─── VPN/Cloak Commands ───
        print("\n🔒 VPN/Cloak Command Routing")
        self.test("'turn on the VPN' -> _is_vpn_toggle_command", a._is_vpn_toggle_command("turn on the VPN"))
        self.test("'put on cloak' -> _is_vpn_toggle_command", a._is_vpn_toggle_command("put on cloak"))
        self.test("'engage cloak' -> _is_vpn_toggle_command", a._is_vpn_toggle_command("engage cloak"))
        self.test("'turn off the cloak' -> _is_vpn_toggle_command", a._is_vpn_toggle_command("turn off the cloak"))
        self.test("'take off cloak' -> _is_vpn_toggle_command", a._is_vpn_toggle_command("take off cloak"))
        self.test("'disable VPN' -> _is_vpn_toggle_command", a._is_vpn_toggle_command("disable VPN"))
        self.test("'vpn status' NOT toggle", not a._is_vpn_toggle_command("vpn status"))
        self.test("'what is a vpn' NOT toggle", not a._is_vpn_toggle_command("what is a vpn"))

        # ─── Maintenance Commands ───
        print("\n🔧 Maintenance Command Routing")
        self.test("'clear tts cache' -> _is_maintenance_command", a._is_maintenance_command("clear tts cache"))
        self.test("'turn on auto cloak' -> _is_maintenance_command", a._is_maintenance_command("turn on auto cloak"))
        self.test("'disable weather warnings' -> _is_maintenance_command", a._is_maintenance_command("disable weather warnings"))
        self.test("'enable vpn monitor' -> _is_maintenance_command", a._is_maintenance_command("enable vpn monitor"))
        self.test("'what is the weather' NOT maintenance", not a._is_maintenance_command("what is the weather"))

        # ─── Protocol Commands ───
        print("\n📡 Protocol Command Routing")
        self.test("'protocol brief' -> _is_protocol_command", a._is_protocol_command("protocol brief"))
        self.test("'enable protocol mode' -> _is_protocol_command", a._is_protocol_command("enable protocol mode"))
        self.test("'turn off protocol mode' -> _is_protocol_command", a._is_protocol_command("turn off protocol mode"))

        # ─── Weather Query Routing ───
        print("\n🌤️ Weather Query Routing")
        self.test("'what is the weather' -> _is_weather_query", a._is_weather_query("what is the weather"))
        self.test("'weather for tomorrow' -> _is_weather_query", a._is_weather_query("weather for tomorrow"))
        self.test("'what is the temperature' -> _is_weather_query", a._is_weather_query("what is the temperature"))
        self.test("'add todo' NOT weather", not a._is_weather_query("add todo"))

        # ─── Forecast Detection ───
        print("\n📅 Forecast Detection")
        self.test("'weather for tomorrow' -> _is_forecast_query", a._is_forecast_query("weather for tomorrow"))
        self.test("'weather forecast' -> _is_forecast_query", a._is_forecast_query("weather forecast"))
        self.test("'what is the weather' NOT forecast", not a._is_forecast_query("what is the weather"))

        # ─── Location Extraction ───
        print("\n🌍 Location Extraction")
        self.test("'weather in Brussels' -> 'brussels'", a._extract_location_from_query("weather in Brussels") == "brussels")
        self.test("'weather for the rest of the day' -> None", a._extract_location_from_query("weather for the rest of the day") is None)
        self.test("'what is the weather for the rest of the day' -> None", a._extract_location_from_query("what is the weather for the rest of the day") is None)
        self.test("'weather tomorrow' -> None", a._extract_location_from_query("weather tomorrow") is None)

        # ─── Gratitude Detection ───
        print("\n🙏 Gratitude Detection")
        self.test("'thank you' -> _is_expression_of_gratitude", a._is_expression_of_gratitude("thank you"))
        self.test("'thanks BT' -> _is_expression_of_gratitude", a._is_expression_of_gratitude("thanks BT"))
        self.test("'thank you BT. Turn on the VPN.' -> gratitude", a._is_expression_of_gratitude("thank you BT. Turn on the VPN."))
        self.test("'what is the weather' NOT gratitude", not a._is_expression_of_gratitude("what is the weather"))

        # ─── Search Query Detection ───
        print("\n🔍 Search Query Detection")
        self.test("'who won the game' -> _is_search_query", a._is_search_query("who won the game"))
        self.test("'latest news' -> _is_search_query", a._is_search_query("latest news"))
        self.test("'turn on the VPN' NOT search", not a._is_search_query("turn on the VPN"))
        self.test("'add todo buy milk' NOT search", not a._is_search_query("add todo buy milk"))
        self.test("'clear tts cache' NOT search", not a._is_search_query("clear tts cache"))
        self.test("'what is the weather' NOT search", not a._is_search_query("what is the weather"))

        # ─── Meta-text Filtering ───
        print("\n🧹 Meta-text Filtering")
        meta_patterns = [
            r'(?i)^\s*bt\s+(?:uses?|initiates?|performs?|executes?|triggers?|activates?|engages?|starts?)\s+.*$',
            r'(?i)^\s*bt\s+(?:is\s+)?(?:now\s+)?(?:using|initiating|performing|executing|triggering|activating|engaging|starting)\s+.*$',
            r'(?i)^\s*(?:simultaneously|meanwhile|at\s+the\s+same\s+time)\s*,?\s*bt\s+.*$',
            r'(?i)^\s*bt\s+(?:also|additionally|furthermore|moreover)\s+.*$',
            r'(?i)^\s*(?:action|system|protocol)\s*:.*$',
        ]
        test_cases = [
            ("BT uses the get_weather action.", True),
            ("BT initiates clearing the cache.", True),
            ("Simultaneously BT engages cloak.", True),
            ("BT also performs a search.", True),
            ("Action: get_weather", True),
            ("The weather is clear today.", False),
            ("Pilot, all systems are operational.", False),
        ]
        for line, should_filter in test_cases:
            matches = any(re.match(pattern, line) for pattern in meta_patterns)
            self.test(f"'{line}' -> {'filtered' if should_filter else 'kept'}", matches == should_filter)

        # ─── Compound Command Routing ───
        print("\n🔗 Compound Command Routing")
        # Test that gratitude + command is detected as compound
        text = "thank you BT. Turn on the VPN."
        is_gratitude = a._is_expression_of_gratitude(text)
        has_vpn = a._is_vpn_toggle_command(text)
        self.test("'thank you BT. Turn on the VPN.' has gratitude", is_gratitude)
        self.test("'thank you BT. Turn on the VPN.' has VPN command", has_vpn)
        self.test("Compound: gratitude + VPN detected together", is_gratitude and has_vpn)

        # Test that todo + travel words doesn't trigger travel
        text = "BT, add to my to do list, go to school, play video games"
        is_todo = a._is_todo_command(text)
        is_travel = a._is_travel_query(text)
        self.test("'add to do list, go to school' -> todo", is_todo)
        self.test("'add to do list, go to school' NOT travel", not is_travel)

        # ─── Summary ───
        print("\n" + "=" * 60)
        print(f"Results: {self.passed} passed, {self.failed} failed")
        if self.failed == 0:
            print("🎉 All integration tests passed!")
        else:
            print("⚠️  Some tests failed. Review the output above.")
        print("=" * 60)
        return self.failed == 0


if __name__ == "__main__":
    tester = CommandRouterTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
