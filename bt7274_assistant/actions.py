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
    try:
        os.system(f'open -a "{app}"')
        return f"Opened {app}."
    except Exception as e:
        return f"Failed to open {app}: {str(e)}"


@register_action("run_script")
def action_run_script(script: str):
    """Run a shell script or command."""
    try:
        result = subprocess.run(script, shell=True, capture_output=True, text=True)
        return f"Script executed. Output: {result.stdout[:200]}"
    except Exception as e:
        return f"Script failed: {str(e)}"


@register_action("set_volume")
def action_set_volume(level: int):
    """Set system volume (0-100)."""
    try:
        os.system(f"osascript -e 'set volume output volume {level}'")
        return f"Volume set to {level}%."
    except Exception as e:
        return f"Failed to set volume: {str(e)}"


@register_action("tell_time")
def action_tell_time():
    """Return current time."""
    try:
        now = datetime.now().strftime("%I:%M %p")
        return f"The current time is {now}."
    except Exception as e:
        return f"Failed to get time: {str(e)}"


@register_action("tell_date")
def action_tell_date():
    """Return current date."""
    try:
        now = datetime.now().strftime("%A, %B %d, %Y")
        return f"Today is {now}."
    except Exception as e:
        return f"Failed to get date: {str(e)}"


@register_action("web_search")
def action_web_search(query: str):
    """Open browser with search query."""
    try:
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        webbrowser.open(url)
        return f"Searching for '{query}'."
    except Exception as e:
        return f"Search failed: {str(e)}"


@register_action("trigger_shortcut")
def action_trigger_shortcut(name: str):
    """Run a macOS Shortcuts automation."""
    try:
        os.system(f'shortcuts run "{name}"')
        return f"Triggered shortcut: {name}."
    except Exception as e:
        return f"Shortcut failed: {str(e)}"


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

@register_action("get_location_structured")
def action_get_location_structured():
    """Return current location as structured data."""
    try:
        from location import LocationProvider
        loc = LocationProvider()
        if loc.update():
            lat_lon = loc.lat_lon
            location_data = {
                "coordinates": {
                    "latitude": lat_lon[0],
                    "longitude": lat_lon[1]
                } if lat_lon else None,
                "city": loc._city,
                "region": loc._region,
                "country": loc._country,
                "formatted": loc.location_str
            }
            return json.dumps(location_data)
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


@register_action("clear_tts_cache")
def action_clear_tts_cache():
    """Clear the TTS response cache."""
    # This action needs access to the assistant instance
    # For now, we'll return a message indicating it should be handled by the pipeline
    return "TTS cache clearing requested. This will be handled by the main pipeline."


@register_action("read_logs")
def action_read_logs(lines: int = 10, date: str = None, search: str = None):
    """Read recent interaction logs with optional search capability."""
    try:
        from interaction_logger import InteractionLogger
        import json
        from datetime import datetime
        from pathlib import Path
        import os
        import glob
        
        log_dir = Path(__file__).parent.parent / "logs"
        
        # If date is specified, read only that day's logs
        if date is not None:
            log_file = log_dir / f"bt7274_interactions_{date}.jsonl"
            if not log_file.exists():
                return f"No logs found for {date}."
            log_files = [log_file]
        else:
            # Read all available log files, sorted by date (newest first)
            log_pattern = log_dir / "bt7274_interactions_*.jsonl"
            log_files = sorted(glob.glob(str(log_pattern)), reverse=True)
            if not log_files:
                return "No log files found."
        
        # Collect entries from all relevant log files
        all_entries = []
        
        for log_file in log_files:
            if len(all_entries) >= lines and date is None:
                break  # Stop if we have enough entries and we're not looking at a specific date
                
            try:
                with open(log_file, 'r') as f:
                    file_lines = f.readlines()
                
                # Process entries from this file (newest first)
                for line in reversed(file_lines):
                    if len(all_entries) >= lines and date is None:
                        break
                        
                    try:
                        entry = json.loads(line.strip())
                        
                        # Apply search filter if provided
                        if search is not None:
                            pilot_msg = entry.get("pilot_message", "").lower()
                            bt_response = entry.get("bt_response", "").lower()
                            search_lower = search.lower()
                            
                            # Skip entries that don't match the search term
                            if search_lower not in pilot_msg and search_lower not in bt_response:
                                continue
                        
                        timestamp = entry.get("timestamp", "Unknown time")
                        pilot_msg = entry.get("pilot_message", "").strip()
                        bt_response = entry.get("bt_response", "").strip()
                        
                        # Extract date from filename or timestamp for sorting
                        if date is None:
                            # Extract date from timestamp for sorting
                            try:
                                entry_date = timestamp.split('T')[0] if 'T' in timestamp else timestamp[:10]
                            except:
                                entry_date = "unknown"
                        else:
                            entry_date = date
                        
                        # Truncate long messages
                        if len(pilot_msg) > 100:
                            pilot_msg = pilot_msg[:100] + "..."
                        if len(bt_response) > 100:
                            bt_response = bt_response[:100] + "..."
                        
                        all_entries.append({
                            "date": entry_date,
                            "entry": f"[{timestamp}] Pilot: \"{pilot_msg}\" → BT: \"{bt_response}\""
                        })
                    except json.JSONDecodeError:
                        # Skip malformed entries
                        continue
            except Exception as file_error:
                # Continue with other files if one fails
                continue
        
        # Sort entries by date (newest first) if reading multiple days
        if date is None:
            all_entries.sort(key=lambda x: x["date"], reverse=True)
        
        # Limit to requested number of lines
        selected_entries = all_entries[:lines] if len(all_entries) >= lines else all_entries
        
        if not selected_entries:
            if search is not None:
                return f"No log entries found matching '{search}'."
            elif date is not None:
                return f"No valid log entries found for {date}."
            else:
                return "No valid log entries found."
        
        # Format the output
        formatted_entries = [entry["entry"] for entry in selected_entries]
        
        if search is not None:
            header = f"Recent logs matching '{search}' ({len(formatted_entries)} entries):"
        elif date is not None:
            header = f"Logs from {date} ({len(formatted_entries)} entries):"
        else:
            header = f"Recent logs ({len(formatted_entries)} entries):"
        
        return header + "\n" + "\n".join(formatted_entries)
        
    except Exception as e:
        return f"Failed to read logs: {str(e)}"
