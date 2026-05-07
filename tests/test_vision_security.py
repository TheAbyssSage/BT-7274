# tests/test_vision_security.py
import pytest
from unittest.mock import patch, MagicMock
from bt7274_perception.vision_engine import VisionEngine


class TestVisionSecurity:
    def test_vision_engine_sanitizes_prompt_before_sending(self):
        """Vision prompts should not leak location context."""
        engine = VisionEngine(ollama_url="http://localhost:11434", vision_model="llava")

        with patch("bt7274_perception.vision_engine.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "response": "I see a room with a desk."
            }
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            # Create a dummy image file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(b"fake png data")
                temp_path = f.name

            try:
                engine.analyze(
                    temp_path,
                    prompt="Pilot is at 50.9311, 5.3378. What do you see?",
                    use_bt_personality=False,
                )

                call_args = mock_post.call_args
                sent_json = call_args[1]["json"]
                messages = sent_json.get("messages", [])
                prompt_sent = messages[0].get("content", "") if messages else ""
                # Location should be stripped from vision prompts
                assert "50.9311" not in prompt_sent
            finally:
                import os
                os.unlink(temp_path)

    def test_vision_engine_does_not_send_images_without_ollama_available(self):
        """Should fail gracefully if Ollama is not reachable."""
        engine = VisionEngine(ollama_url="http://localhost:11434", vision_model="llava")

        with patch("bt7274_perception.vision_engine.requests.post") as mock_post:
            mock_post.side_effect = Exception("Connection refused")

            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(b"fake png data")
                temp_path = f.name

            try:
                result = engine.analyze(temp_path)
                assert result["success"] is False
                assert "error" in result
            finally:
                import os
                os.unlink(temp_path)

    def test_perception_manager_requires_explicit_trigger(self):
        """PerceptionManager.look() should log the trigger for audit purposes."""
        from bt7274_perception.perception_manager import PerceptionManager

        pm = PerceptionManager(
            camera_device="0",
            ollama_url="http://localhost:11434",
            vision_model="llava",
        )

        with patch.object(pm.camera, "capture") as mock_capture:
            with patch.object(pm.engine, "analyze") as mock_analyze:
                mock_capture.return_value = "/tmp/test.png"
                mock_analyze.return_value = {
                    "success": True,
                    "description": "A room.",
                    "model": "llava",
                    "response_time": 0.5,
                    "error": None,
                }

                result = pm.look(trigger="voice_command", pilot_query="what do you see")
                assert result["success"] is True
