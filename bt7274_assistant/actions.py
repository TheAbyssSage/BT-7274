"""
Action handler for executing tasks based on LLM intent.
"""

import os
import subprocess
import webbrowser
import requests
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

        import re
        import json

        # Try to parse the entire string as JSON first
        try:
            action_data = json.loads(llm_response.strip())
            if "action" in action_data:
                return self._execute_action(action_data)
        except (json.JSONDecodeError, ValueError):
            pass

        # Match JSON code blocks
        match = re.search(r'```json\s*(.*?)\s*```', llm_response, re.DOTALL)
        if not match:
            # Try inline JSON (handle nested braces)
            match = re.search(r'\{[\s\S]*?"action"[\s\S]*?\}', llm_response)

        if not match:
            return None

        try:
            action_data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

        return self._execute_action(action_data)

    def _execute_action(self, action_data: dict) -> Optional[str]:
        """Execute a parsed action."""
        import json
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

    def execute(self, action_name: str, **params) -> Optional[str]:
        """Execute an action directly by name (bypasses JSON parsing)."""
        if not self.enabled:
            return None
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


@register_action("tell_date")
def action_tell_date():
    """Return current date."""
    now = datetime.now().strftime("%A, %B %d, %Y")
    return f"Today is {now}."


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


@register_action("search_web")
def action_search_web(query: str):
    """Search the web using DuckDuckGo and return top results."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results:
            return "No results found."
        snippets = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            snippets.append(f"{title}: {body}")
        return " | ".join(snippets)
    except Exception as e:
        return f"Search failed: {str(e)}"


@register_action("get_location")
def action_get_location():
    """Return current location."""
    try:
        from location import LocationProvider
        loc = LocationProvider()
        if loc.update():
            lat_lon = loc.lat_lon
            coords = f"Coordinates: {lat_lon[0]:.4f}, {lat_lon[1]:.4f}. " if lat_lon else ""
            return f"{coords}Location: {loc.location_str}."
        return "Location unavailable."
    except Exception as e:
        return f"Location error: {str(e)}"


@register_action("get_weather")
def action_get_weather():
    """Fetch current weather from Open-Meteo API using cached location."""
    try:
        from location import LocationProvider
        loc = LocationProvider()
        if not loc.update():
            return "Unable to determine location for weather."

        lat_lon = loc.lat_lon
        if not lat_lon:
            return "Location coordinates unavailable."

        lat, lon = lat_lon
        return _fetch_weather(lat, lon)
    except Exception as e:
        return f"Weather data unavailable: {str(e)}"


@register_action("get_weather_for_location")
def action_get_weather_for_location(location: str):
    """Fetch weather for a specific location using geocoding."""
    try:
        # Geocode the location string to lat/lon
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location.replace(' ', '+')}&count=1"
        geo_resp = requests.get(geo_url, timeout=10)
        geo_data = geo_resp.json()
        results = geo_data.get("results", [])
        if not results:
            return f"Unable to find location: {location}"
        
        lat = results[0]["latitude"]
        lon = results[0]["longitude"]
        city = results[0].get("name", location)
        
        return _fetch_weather(lat, lon, city)
    except Exception as e:
        return f"Weather data unavailable: {str(e)}"


def _fetch_weather(lat: float, lon: float, city_name: str = None):
    """Helper to fetch weather from Open-Meteo."""
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&current_weather=true"
    )
    resp = requests.get(url, timeout=10)
    data = resp.json()
    current = data.get("current_weather", {})
    temp = current.get("temperature")
    wind = current.get("windspeed")
    code = current.get("weathercode")

    # WMO weather code mapping (simplified)
    conditions = {
        0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
        45: "fog", 48: "depositing rime fog",
        51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
        61: "slight rain", 63: "moderate rain", 65: "heavy rain",
        71: "slight snow", 73: "moderate snow", 75: "heavy snow",
        80: "rain showers", 81: "moderate showers", 82: "violent showers",
        95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
    }
    condition = conditions.get(code, "unknown conditions")
    
    loc_str = city_name if city_name else "your location"

    return (
        f"Current weather in {loc_str}: {condition}, "
        f"{temp}°C, wind {wind} km/h."
    )
