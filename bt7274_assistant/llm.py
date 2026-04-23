"""
LLM clients for Ollama and Cloud AI (BT-7274 personality).
"""

import json
import re
import os
from typing import Optional

import requests


class OllamaClient:
    def __init__(self, config: dict):
        self.config = config
        self.model = config.get("model", "bt7274")
        self.url = config.get("url", "http://localhost:11434")
        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens", 150)
        self.system_prompt = config.get("system_prompt", "")
        self.history = []

    def chat(self, message: str) -> str:
        """Send a message to Ollama and return the response text."""
        # Build messages
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": message})

        try:
            response = requests.post(
                f"{self.url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": self.max_tokens,
                    }
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            reply = data.get("message", {}).get("content", "")

            # Update history (keep last 10 exchanges)
            self.history.append({"role": "user", "content": message})
            self.history.append({"role": "assistant", "content": reply})
            if len(self.history) > 20:
                self.history = self.history[-20:]

            return reply.strip()

        except requests.exceptions.ConnectionError:
            return "Pilot, I am unable to connect to my neural network. Is Ollama running?"
        except Exception as e:
            return f"Pilot, an error occurred in my systems: {str(e)}"

    def extract_action(self, text: str) -> Optional[dict]:
        """Extract JSON action block from LLM response."""
        # Look for JSON code blocks
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Look for inline JSON
        json_match = re.search(r'\{[^{}]*"action"[^{}]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return None


class CloudLLMClient:
    def __init__(self, config: dict):
        self.config = config
        self.model = config.get("model", "gpt-oss:120b-cloud")
        self.url = config.get("url", "http://localhost:11434")
        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens", 150)
        self.system_prompt = config.get("system_prompt", "")
        self.history = []

    def chat(self, message: str) -> str:
        """Send a message to cloud Ollama and return the response text."""
        # Build messages
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": message})

        try:
            response = requests.post(
                f"{self.url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": self.max_tokens,
                    }
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            reply = data.get("message", {}).get("content", "")

            # Update history (keep last 10 exchanges)
            self.history.append({"role": "user", "content": message})
            self.history.append({"role": "assistant", "content": reply})
            if len(self.history) > 20:
                self.history = self.history[-20:]

            return reply.strip()

        except requests.exceptions.ConnectionError:
            return "Pilot, I am unable to connect to my neural network. Is the internet connection stable?"
        except Exception as e:
            return f"Pilot, an error occurred in my systems: {str(e)}"

    def extract_action(self, text: str) -> Optional[dict]:
        """Extract JSON action block from LLM response."""
        # Look for JSON code blocks
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Look for inline JSON
        json_match = re.search(r'\{[^{}]*"action"[^{}]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return None
