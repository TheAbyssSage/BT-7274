"""Tests for autonomous BT memory logging."""

import sys
import time
import unittest
from unittest.mock import MagicMock, patch

# Guard against missing optional dependencies when importing pipeline modules
sys.modules.setdefault("whisper", MagicMock())
sys.modules.setdefault("sklearn", MagicMock())
sys.modules.setdefault("sklearn.feature_extraction", MagicMock())
sys.modules.setdefault("sklearn.feature_extraction.text", MagicMock())
sys.modules.setdefault("sklearn.metrics", MagicMock())
sys.modules.setdefault("sklearn.metrics.pairwise", MagicMock())
sys.modules.setdefault("torch", MagicMock())
sys.modules.setdefault("TTS", MagicMock())
sys.modules.setdefault("TTS.api", MagicMock())
sys.modules.setdefault("soundfile", MagicMock())
sys.modules.setdefault("sounddevice", MagicMock())
_mock_numpy = MagicMock()
_mock_numpy.__version__ = "1.26.0"
sys.modules.setdefault("numpy", _mock_numpy)
sys.modules.setdefault("scipy", MagicMock())
sys.modules.setdefault("scipy.signal", MagicMock())

from bt7274.bt7274_assistant.pipeline.command_processing import CommandProcessingMixin


class TestAutonomousLogging(unittest.TestCase):
    def _make_assistant(self):
        """Build a minimal mock assistant with autonomous logging state."""
        assistant = MagicMock()
        assistant.autonomous_log_enabled = True
        assistant.autonomous_log_cooldown_until = 0.0
        assistant.autonomous_logs_this_session = 0
        assistant.autonomous_log_max_per_session = 10
        assistant.autonomous_log_cooldown_seconds = 60
        assistant._last_autonomous_log_hash = ""
        assistant.interaction_count = 5
        assistant.pilot_trust_level = 2
        assistant.errors_this_interaction = []
        assistant.actions_this_session = ["get_weather"]
        assistant.config = {
            "llm": {
                "autonomous_logging": {
                    "enabled": True,
                    "cooldown_seconds": 60,
                    "max_per_session": 10,
                    "decision_prompt": (
                        "Decide: {pilot_message} | {bt_response} | {context_summary}"
                    ),
                }
            }
        }
        return assistant

    def test_should_log_when_llm_says_yes(self):
        """If LLM returns log:true, decision should be returned."""
        assistant = self._make_assistant()
        assistant.llm = MagicMock()
        assistant.llm.chat.return_value = '{"log": true, "reason": "test", "content": "Pilot asked about mission."}'
        assistant._report_error = MagicMock()

        decision = CommandProcessingMixin._should_log_autonomously(assistant, "hello", "hi")
        self.assertIsNotNone(decision)
        self.assertTrue(decision["log"])
        self.assertEqual(decision["content"], "Pilot asked about mission.")

    def test_should_not_log_when_disabled(self):
        """If autonomous logging is disabled, return None."""
        assistant = self._make_assistant()
        assistant.autonomous_log_enabled = False
        decision = CommandProcessingMixin._should_log_autonomously(assistant, "hello", "hi")
        self.assertIsNone(decision)

    def test_should_not_log_during_cooldown(self):
        """If cooldown is active, return None."""
        assistant = self._make_assistant()
        assistant.autonomous_log_cooldown_until = time.time() + 999
        decision = CommandProcessingMixin._should_log_autonomously(assistant, "hello", "hi")
        self.assertIsNone(decision)

    def test_should_not_log_when_max_reached(self):
        """If max per session reached, return None."""
        assistant = self._make_assistant()
        assistant.autonomous_logs_this_session = 10
        decision = CommandProcessingMixin._should_log_autonomously(assistant, "hello", "hi")
        self.assertIsNone(decision)

    def test_should_not_log_duplicate(self):
        """If same interaction hash, return None."""
        assistant = self._make_assistant()
        import hashlib
        assistant._last_autonomous_log_hash = hashlib.md5(b"hello|hi").hexdigest()[:16]
        decision = CommandProcessingMixin._should_log_autonomously(assistant, "hello", "hi")
        self.assertIsNone(decision)

    def test_perform_autonomous_log_executes_action(self):
        """_perform_autonomous_log should call make_log action when decision is yes."""
        assistant = self._make_assistant()
        assistant.llm = MagicMock()
        assistant.llm.chat.return_value = '{"log": true, "reason": "test", "content": "Mission update."}'
        assistant.actions = MagicMock()
        assistant.actions.execute.return_value = "Log entry saved."
        assistant._report_error = MagicMock()
        assistant.status = MagicMock()
        # Bind the real method so _perform_autonomous_log uses it internally
        assistant._should_log_autonomously = CommandProcessingMixin._should_log_autonomously.__get__(assistant, MagicMock)

        result = CommandProcessingMixin._perform_autonomous_log(assistant, "status?", "All systems green.")
        self.assertEqual(result, "Log entry saved.")
        assistant.actions.execute.assert_called_once()
        call_args = assistant.actions.execute.call_args
        self.assertEqual(call_args.kwargs["log_type"], "bt")
        self.assertEqual(call_args.kwargs["text"], "Mission update.")


if __name__ == "__main__":
    unittest.main()
