# tests/test_llm_security.py
import pytest
from unittest.mock import patch, MagicMock
from bt7274_assistant.llm import OllamaClient, CloudLLMClient


class TestOllamaClientSecurity:
    def test_chat_sanitizes_pii_before_sending(self):
        config = {
            "model": "bt7274",
            "url": "http://localhost:11434",
            "temperature": 0.7,
            "max_tokens": 150,
            "system_prompt": "You are BT-7274.",
        }
        client = OllamaClient(config)

        with patch("bt7274_assistant.llm.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "Copy that, Pilot."}
            }
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            client.chat("my email is pilot@frontier.mil and I need help")

            call_args = mock_post.call_args
            sent_json = call_args[1]["json"]
            messages = sent_json["messages"]
            user_message = messages[-1]["content"]
            assert "pilot@frontier.mil" not in user_message
            assert "[REDACTED" in user_message

    def test_chat_sanitizes_ip_address(self):
        config = {
            "model": "bt7274",
            "url": "http://localhost:11434",
            "temperature": 0.7,
            "max_tokens": 150,
            "system_prompt": "You are BT-7274.",
        }
        client = OllamaClient(config)

        with patch("bt7274_assistant.llm.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "Acknowledged."}
            }
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            client.chat("server at 10.0.0.1 is down")

            call_args = mock_post.call_args
            sent_json = call_args[1]["json"]
            messages = sent_json["messages"]
            user_message = messages[-1]["content"]
            assert "10.0.0.1" not in user_message
            assert "[REDACTED" in user_message

    def test_chat_preserves_clean_text(self):
        config = {
            "model": "bt7274",
            "url": "http://localhost:11434",
            "temperature": 0.7,
            "max_tokens": 150,
            "system_prompt": "You are BT-7274.",
        }
        client = OllamaClient(config)

        with patch("bt7274_assistant.llm.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "Ready, Pilot."}
            }
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            client.chat("what is the mission status")

            call_args = mock_post.call_args
            sent_json = call_args[1]["json"]
            messages = sent_json["messages"]
            user_message = messages[-1]["content"]
            assert user_message == "what is the mission status"

    def test_system_prompt_is_not_sanitized(self):
        """System prompt should pass through unchanged — it's authored, not user input."""
        config = {
            "model": "bt7274",
            "url": "http://localhost:11434",
            "temperature": 0.7,
            "max_tokens": 150,
            "system_prompt": "You are BT-7274. Your pilot is Roamer.",
        }
        client = OllamaClient(config)

        with patch("bt7274_assistant.llm.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "Ready."}
            }
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            client.chat("hello")

            call_args = mock_post.call_args
            sent_json = call_args[1]["json"]
            messages = sent_json["messages"]
            system_message = messages[0]["content"]
            assert "Roamer" in system_message


class TestCloudLLMClientSecurity:
    def test_chat_sanitizes_pii_before_sending(self):
        config = {
            "model": "gpt-oss:120b-cloud",
            "url": "http://localhost:11434",
            "temperature": 0.7,
            "max_tokens": 120,
            "system_prompt": "You are BT-7274.",
        }
        client = CloudLLMClient(config)

        with patch("bt7274_assistant.llm.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "Copy that, Pilot."}
            }
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            client.chat("call 555-123-4567 for backup")

            call_args = mock_post.call_args
            sent_json = call_args[1]["json"]
            messages = sent_json["messages"]
            user_message = messages[-1]["content"]
            assert "555-123-4567" not in user_message
            assert "[REDACTED" in user_message
