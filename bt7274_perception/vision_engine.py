"""
Vision Engine for BT-7274 Perception.

Analyzes captured camera frames using Ollama vision models.
Falls back gracefully if no vision model is available.
"""

import base64
import json
import time
from pathlib import Path
from typing import Optional

import requests


class VisionEngine:
    """
    Analyzes images via Ollama vision-capable models.

    Expects an Ollama instance running locally with a vision model
    such as llava, moondream, or bakllava.
    """

    DEFAULT_VISION_PROMPT = (
        "Describe this scene in 2-4 concise sentences. "
        "Focus on: the main objects, people, activities, and the overall environment. "
        "Be factual and direct."
    )

    BT_PERSONALITY_PROMPT = (
        "You are BT-7274, a Vanguard-class Titan. Describe what you see through your "
        "optical sensors in 2-4 concise sentences. Be tactical, precise, and slightly dry. "
        "Address the user as 'Pilot'. Focus on objects, people, activities, and environment."
    )

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        vision_model: str = "llava",
        timeout: float = 60.0,
    ):
        self.ollama_url = ollama_url.rstrip("/")
        self.vision_model = vision_model
        self.timeout = timeout
        self._available_models: Optional[list[str]] = None

    def _encode_image(self, image_path: str) -> str:
        """Base64-encode an image file for the Ollama API."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _list_models(self) -> list[str]:
        """Fetch available models from Ollama."""
        if self._available_models is not None:
            return self._available_models
        try:
            resp = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            self._available_models = [m.get("name", "") for m in data.get("models", [])]
            return self._available_models
        except Exception:
            self._available_models = []
            return []

    def is_vision_model_available(self) -> bool:
        """Check if the configured vision model is pulled in Ollama."""
        models = self._list_models()
        return any(self.vision_model in m for m in models)

    def suggest_vision_model(self) -> str:
        """Return installation instructions for a vision model."""
        return (
            f"Vision model '{self.vision_model}' not found in Ollama.\n"
            "Install one with:\n"
            "  ollama pull llava          # general purpose\n"
            "  ollama pull moondream      # lightweight\n"
            "  ollama pull bakllava       # high quality"
        )

    def analyze(
        self,
        image_path: str,
        prompt: Optional[str] = None,
        use_bt_personality: bool = True,
    ) -> dict:
        """
        Analyze an image and return structured results.

        Args:
            image_path: Path to the image file.
            prompt: Custom prompt. If None, uses default or BT personality.
            use_bt_personality: If True, prepends BT personality to the prompt.

        Returns:
            Dict with keys:
                - success (bool)
                - description (str) — the vision model's description
                - model (str) — model used
                - response_time (float) — seconds
                - error (str|None) — error message if failed
        """
        if not Path(image_path).exists():
            return {
                "success": False,
                "description": "",
                "model": self.vision_model,
                "response_time": 0.0,
                "error": f"Image not found: {image_path}",
            }

        if not self.is_vision_model_available():
            return {
                "success": False,
                "description": "",
                "model": self.vision_model,
                "response_time": 0.0,
                "error": self.suggest_vision_model(),
            }

        # Build prompt
        if prompt is None:
            prompt = self.BT_PERSONALITY_PROMPT if use_bt_personality else self.DEFAULT_VISION_PROMPT
        elif use_bt_personality:
            prompt = f"{self.BT_PERSONALITY_PROMPT}\n\n{prompt}"

        # Encode image
        try:
            b64_image = self._encode_image(image_path)
        except Exception as e:
            return {
                "success": False,
                "description": "",
                "model": self.vision_model,
                "response_time": 0.0,
                "error": f"Failed to encode image: {e}",
            }

        # Call Ollama vision API
        start = time.time()
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.vision_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [b64_image],
                        }
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.4,
                        "num_predict": 120,
                    },
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            description = data.get("message", {}).get("content", "").strip()
            elapsed = round(time.time() - start, 3)

            return {
                "success": True,
                "description": description,
                "model": self.vision_model,
                "response_time": elapsed,
                "error": None,
            }

        except requests.exceptions.ConnectionError:
            elapsed = round(time.time() - start, 3)
            return {
                "success": False,
                "description": "",
                "model": self.vision_model,
                "response_time": elapsed,
                "error": "Ollama is not running. Start it with: ollama serve",
            }
        except Exception as e:
            elapsed = round(time.time() - start, 3)
            return {
                "success": False,
                "description": "",
                "model": self.vision_model,
                "response_time": elapsed,
                "error": f"Vision analysis failed: {e}",
            }

    def analyze_quick(
        self,
        image_path: str,
        prompt: Optional[str] = None,
    ) -> str:
        """
        Quick analysis returning just the description string.

        Returns:
            Description on success, error message on failure.
        """
        result = self.analyze(image_path, prompt=prompt)
        if result["success"]:
            return result["description"]
        return f"Vision systems offline: {result['error']}"
