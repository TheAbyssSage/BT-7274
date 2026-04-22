"""
Action handler for executing tasks based on LLM intent.
"""

import os
import subprocess
import webbrowser
from datetime import datetime
from typing import Optional, Callable
from functools import wraps


# Registry of available actions
_ACTIONS: dict[str, Callable] = {}


def register_action(name: str):
    """Decorator to register an action handler."""
    def decorator(func: Callable):
        _ACTIONS[name] = func
        return func
    return decorator


class ActionHandler:
    def __init__(self, config: dict):
        self.config = config
        self.enabled = config.get("enabled", True)
        self.allowed = set(config.get("allowed_commands", []))

    def parse_and_execute(self, llm_response: str) -> Optional[str]:
        """Parse action from LLM response and execute if allowed."""
        if not self.enabled:
            return None

        # Try to extract JSON action
        import re
        import json

        # Match JSON code blocks
        match = re.search(r'```json\s*(.*?)\s*```', llm_response, re.DOTALL)
        if not match:
            # Try inline JSON
            match = re.search(r'(\{[^{}]*"action"[^{}]*\})', llm_response)

        if not match:
            return None

        try:
            action_data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

        action_name = action_data.get("action")
        params = action_data.get("params", {})

        if action_name not in self.allowed:
            return f"Action '{action_name}' is not allowed."

        handler = _ACTIONS.get(action_name)
        if not handler:
            return f"Unknown action: {action_name}"

        try:
            result = handler(**params)
            return result or f"Executed: {action_name}"
        except Exception as e:
            return f"Action failed: {str(e)}"


# ─── Built-in Actions ───────────────────────────────────────────────

@register_action("say")
def action_say(text: str):
    """Speak arbitrary text (handled by TTS, this is a no-op for actions)."""
    return None


@register_action("open")
def action_open(app: str):
    """Open a macOS application."""
    os.system(f'open -a "{app}"')
    return f"Opened {app}."


@register_action("run_script")
def action_run_script(script: str):
    """Run a shell script or command."""
    result = subprocess.run(script, shell=True, capture_output=True, text=True)
    return f"Script executed. Output: {result.stdout[:200]}"


@register_action("set_volume")
def action_set_volume(level: int):
    """Set system volume (0-100)."""
    os.system(f"osascript -e 'set volume output volume {level}'")
    return f"Volume set to {level}%."


@register_action("tell_time")
def action_tell_time():
    """Return current time."""
    now = datetime.now().strftime("%I:%M %p")
    return f"The current time is {now}."


@register_action("web_search")
def action_web_search(query: str):
    """Open browser with search query."""
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    webbrowser.open(url)
    return f"Searching for '{query}'."


@register_action("trigger_shortcut")
def action_trigger_shortcut(name: str):
    """Run a macOS Shortcuts automation."""
    os.system(f'shortcuts run "{name}"')
    return f"Triggered shortcut: {name}."
