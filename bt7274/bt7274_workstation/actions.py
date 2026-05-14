"""
Action handler for executing tasks based on LLM intent.
"""

import os
import json
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
        if match:
            try:
                action_data = json.loads(match.group(1))
                if "action" in action_data:
                    return self._execute_action(action_data)
            except json.JSONDecodeError:
                pass

        # Try inline JSON with "action" key (handle nested braces)
        match = re.search(r'\{[\s\S]*?"action"[\s\S]*?\}', llm_response)
        if match:
            try:
                action_data = json.loads(match.group(0))
                if "action" in action_data:
                    return self._execute_action(action_data)
            except json.JSONDecodeError:
                pass

        # Handle LLM output like: make_log {"content":"...", "log_type":"bt"}
        # or: add_todo {"task":"..."}
        action_prefix_match = re.search(
            r'^(\w+)\s*(\{[\s\S]*?\})',
            llm_response.strip()
        )
        if action_prefix_match:
            action_name = action_prefix_match.group(1)
            json_str = action_prefix_match.group(2)
            try:
                params = json.loads(json_str)
                action_data = {"action": action_name, "params": params}
                return self._execute_action(action_data)
            except json.JSONDecodeError:
                pass

        return None

    def _execute_action(self, action_data: dict) -> Optional[str]:
        """Execute a parsed action."""
        import json
        action_name = action_data.get("action") or ""
        params = action_data.get("params", {})

        if action_name not in self.allowed:
            return f"Action '{action_name}' is not allowed."

        handler = _ACTIONS.get(action_name) if _ACTIONS else None
        if not handler:
            return f"Unknown action: {action_name}"

        try:
            # Ensure params is a dict and handle None values
            safe_params = {}
            if params and isinstance(params, dict):
                for key, value in params.items():
                    if key is not None and value is not None:
                        safe_params[str(key)] = value
            
            result = handler(**safe_params) if handler and safe_params else None
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
    from bt7274.bt7274_workstation.security_guard import SecurityGuard
    guard = SecurityGuard()
    is_safe, reason = guard.validate_shell_command(script)
    if not is_safe:
        guard.audit("blocked_command", {"command": script[:200], "reason": reason})
        return f"Command blocked for security: {reason}"
    try:
        result = subprocess.run(script, shell=True, capture_output=True, text=True, timeout=30)
        return f"Script executed. Output: {result.stdout[:200]}"
    except subprocess.TimeoutExpired:
        return "Script timed out after 30 seconds."
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
    import time
    start_time = time.time()
    
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results:
            # Log the search even when no results found
            try:
                from bt7274.bt7274_workstation.search_logger import SearchLogger
                logger = SearchLogger()
                logger.log_search(
                    query=query,
                    results="No results found.",
                    success=False,
                    response_time=time.time() - start_time
                )
            except Exception:
                pass  # Don't fail the action if logging fails
            return "No results found."
        snippets = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            snippets.append(f"{title}: {body}")
        result_text = " | ".join(snippets)
        
        # Log the successful search
        try:
            from bt7274.bt7274_workstation.search_logger import SearchLogger
            logger = SearchLogger()
            logger.log_search(
                query=query,
                results=result_text,
                success=True,
                response_time=time.time() - start_time
            )
        except Exception:
            pass  # Don't fail the action if logging fails
            
        return result_text
    except Exception as e:
        # Log the failed search
        try:
            from bt7274.bt7274_workstation.search_logger import SearchLogger
            logger = SearchLogger()
            logger.log_search(
                query=query,
                results="",
                success=False,
                error_message=str(e),
                response_time=time.time() - start_time
            )
        except Exception:
            pass  # Don't fail the action if logging fails
        return f"Search failed: {str(e)}"


@register_action("get_location")
def action_get_location():
    """Return current location."""
    try:
        from bt7274.bt7274_workstation.location import LocationProvider
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
        from bt7274.bt7274_workstation.location import LocationProvider
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
        from bt7274.bt7274_workstation.location import LocationProvider
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
        
        lat = results[0].get("latitude", 0.0) if results and len(results) > 0 else 0.0
        lon = results[0].get("longitude", 0.0) if results and len(results) > 0 else 0.0
        city = results[0].get("name", location) if results and len(results) > 0 else (location or "")
        
        return _fetch_weather(lat or 0.0, lon or 0.0, city or "")
    except Exception as e:
        return f"Weather data unavailable: {str(e)}"


@register_action("get_weather_forecast")
def action_get_weather_forecast(days: int = 3, location: str | None = None):
    """Fetch upcoming weather forecast for the current or a specified location."""
    try:
        from bt7274.bt7274_workstation.location import LocationProvider
        loc = LocationProvider()

        if location:
            # Geocode the provided location string
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location.replace(' ', '+')}&count=1"
            geo_resp = requests.get(geo_url, timeout=10)
            geo_data = geo_resp.json()
            results = geo_data.get("results", [])
            if not results:
                return f"Unable to find location: {location}"
            lat = results[0].get("latitude", 0.0) if results and len(results) > 0 else 0.0
            lon = results[0].get("longitude", 0.0) if results and len(results) > 0 else 0.0
            city = results[0].get("name", location) if results and len(results) > 0 else location or ""
        else:
            if not loc.update():
                return "Unable to determine location for forecast."
            lat_lon = loc.lat_lon if loc else None
            if not lat_lon:
                return "Location coordinates unavailable."
            lat, lon = lat_lon if lat_lon else (0.0, 0.0)
            city = (loc._city or "your location") if loc else "your location"

        return _fetch_weather_forecast(lat or 0.0, lon or 0.0, city or "your location" if city else "your location", days or 3)
    except Exception as e:
        return f"Forecast data unavailable: {str(e)}"


def _fetch_weather(lat: float, lon: float, city_name: str | None = None):
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


def _fetch_weather_forecast(lat: float, lon: float, city_name: str | None = None, days: int = 3):
    """Helper to fetch daily weather forecast from Open-Meteo."""
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max&"
        f"timezone=auto&forecast_days={days}"
    )
    resp = requests.get(url, timeout=10)
    data = resp.json()
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    max_temps = daily.get("temperature_2m_max", [])
    min_temps = daily.get("temperature_2m_min", [])
    codes = daily.get("weathercode", [])
    rain_probs = daily.get("precipitation_probability_max", [])

    conditions = {
        0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
        45: "fog", 48: "depositing rime fog",
        51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
        61: "slight rain", 63: "moderate rain", 65: "heavy rain",
        71: "slight snow", 73: "moderate snow", 75: "heavy snow",
        80: "rain showers", 81: "moderate showers", 82: "violent showers",
        95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
    }

    loc_str = city_name if city_name else "your location"
    lines = [f"Weather forecast for {loc_str}:"]

    for i in range(len(dates)):
        date = dates[i]
        max_t = max_temps[i] if i < len(max_temps) else "?"
        min_t = min_temps[i] if i < len(min_temps) else "?"
        code = codes[i] if i < len(codes) else None
        rain = rain_probs[i] if i < len(rain_probs) else "?"
        condition = conditions.get(code, "unknown conditions") if conditions and code is not None else "unknown conditions"
        lines.append(
            f"{date}: {condition}, {min_t}°C to {max_t}°C, {rain}% chance of rain."
        )

    return " ".join(lines)


@register_action("clear_tts_cache")
def action_clear_tts_cache():
    """Clear the TTS response cache."""
    # This action needs access to the assistant instance
    # For now, we'll return a message indicating it should be handled by the pipeline
    return "TTS cache clearing requested. This will be handled by the main pipeline."


@register_action("read_logs")
def action_read_logs(lines: int = 10, date: str | None = None, search: str | None = None):
    """Read recent interaction logs with optional search capability."""
    try:
        from bt7274.bt7274_workstation.interaction_logger import InteractionLogger
        import json
        from datetime import datetime
        from pathlib import Path
        import os
        import glob
        
        log_dir = Path(__file__).parent.parent / "logs" / "bt-pilot_interactions"
        
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


@register_action("make_log")
def action_make_log(text: str, name: str = "pilot", tags: str | None = None, log_type: str = "pilot"):
    """
    Append a free-form log entry for the Pilot or BT.

    Args:
        text: The raw log text to record.
        name: Optional log name (used in filename). Defaults to "pilot".
        tags: Optional comma-separated tags (e.g., "mission,personal").
        log_type: "pilot" for pilot logs, "bt" for BT internal logs.
    """
    try:
        from bt7274.bt7274_workstation.pilot_logger import PilotLogger
        logger = PilotLogger()
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        if log_type.lower() == "bt":
            return logger.log_bt(text, name=name, tags=tag_list)
        return logger.log_pilot(text, name=name, tags=tag_list)
    except Exception as e:
        return f"Failed to make log: {str(e)}"


@register_action("read_bt_logs")
def action_read_bt_logs(lines: int = 20, date: str | None = None):
    """
    Read BT's own personal memory logs.

    Args:
        lines: Number of recent entries to read.
        date: Optional specific date (YYYY-MM-DD) to read.
    """
    try:
        from bt7274.bt7274_workstation.pilot_logger import PilotLogger
        logger = PilotLogger()
        return logger.read_bt_logs(lines=lines, date=date)
    except Exception as e:
        return f"Failed to read BT logs: {str(e)}"


@register_action("delete_logs")
def action_delete_logs(log_type: str = "pilot", name: str | None = None, date: str | None = None):
    """
    Delete log files.

    Args:
        log_type: "pilot" for pilot logs, "bt" for BT internal logs.
        name: Optional specific log name to delete.
        date: Optional specific date (YYYY-MM-DD) to delete.
    """
    try:
        from bt7274.bt7274_workstation.pilot_logger import PilotLogger
        logger = PilotLogger()
        if log_type.lower() == "bt":
            return logger.delete_bt_logs(name=name, date=date)
        return logger.delete_pilot_logs(name=name, date=date)
    except Exception as e:
        return f"Failed to delete logs: {str(e)}"


# ─── Protocol Brief Actions ─────────────────────────────────────────

@register_action("protocol_brief")
def action_protocol_brief(name: str = "pilot"):
    """Generate a protocol brief summary of goals, status, and suggestions."""
    try:
        from bt7274.bt7274_workstation.protocol_brief import ProtocolBrief
        pb = ProtocolBrief()
        return pb.get_brief(name=name)
    except Exception as e:
        return f"Protocol brief unavailable: {str(e)}"


@register_action("add_todo")
def action_add_todo(text: str, name: str = "pilot", priority: str = "normal"):
    """Add a task to the pilot to-do list."""
    try:
        from bt7274.bt7274_workstation.protocol_brief import ProtocolBrief
        pb = ProtocolBrief()
        return pb.add_todo(text=text, name=name, priority=priority)
    except Exception as e:
        return f"Failed to add to-do: {str(e)}"


@register_action("complete_todo")
def action_complete_todo(item_id: int, name: str = "pilot"):
    """Mark a to-do item as completed."""
    try:
        from bt7274.bt7274_workstation.protocol_brief import ProtocolBrief
        pb = ProtocolBrief()
        return pb.complete_todo(item_id=item_id, name=name)
    except Exception as e:
        return f"Failed to complete to-do: {str(e)}"


@register_action("remove_todo")
def action_remove_todo(item_id: int, name: str = "pilot"):
    """Remove a to-do item."""
    try:
        from bt7274.bt7274_workstation.protocol_brief import ProtocolBrief
        pb = ProtocolBrief()
        return pb.remove_todo(item_id=item_id, name=name)
    except Exception as e:
        return f"Failed to remove to-do: {str(e)}"


@register_action("list_todo")
def action_list_todo(name: str = "pilot", show_completed: bool = False):
    """List pilot to-do items."""
    try:
        from bt7274.bt7274_workstation.protocol_brief import ProtocolBrief
        pb = ProtocolBrief()
        return pb.list_todo(name=name, show_completed=show_completed)
    except Exception as e:
        return f"Failed to list to-do items: {str(e)}"


@register_action("clear_todo")
def action_clear_todo(name: str = "pilot"):
    """Clear all completed to-do items."""
    try:
        from bt7274.bt7274_workstation.protocol_brief import ProtocolBrief
        pb = ProtocolBrief()
        return pb.clear_todo(name=name)
    except Exception as e:
        return f"Failed to clear to-do items: {str(e)}"


@register_action("add_note")
def action_add_note(text: str, name: str = "pilot", tags: str | None = None):
    """Append a note to the personal log."""
    try:
        from bt7274.bt7274_workstation.protocol_brief import ProtocolBrief
        pb = ProtocolBrief()
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        return pb.add_note(text=text, name=name, tags=tag_list)
    except Exception as e:
        return f"Failed to add note: {str(e)}"


@register_action("list_notes")
def action_list_notes(name: str = "pilot", lines: int = 10, tag: str | None = None):
    """Read recent personal notes."""
    try:
        from bt7274.bt7274_workstation.protocol_brief import ProtocolBrief
        pb = ProtocolBrief()
        return pb.list_notes(name=name, lines=lines, tag=tag)
    except Exception as e:
        return f"Failed to list notes: {str(e)}"


# ─── Vision / Perception Actions ────────────────────────────────────

@register_action("look")
def action_look(pilot_query: str | None = None):
    """
    Capture a frame from the camera and analyze what BT-7274 sees.

    Args:
        pilot_query: The Pilot's exact words that triggered the look.

    Returns:
        Description of the scene, or error message.
    """
    try:
        from bt7274.bt7274_perception import PerceptionManager
        pm = PerceptionManager()
        result = pm.look(trigger="voice_command", pilot_query=pilot_query)
        if result["success"]:
            return result["description"]
        return f"Optical sensors offline: {result.get('error', 'Unknown error')}"
    except Exception as e:
        return f"Vision system error: {str(e)}"


@register_action("vision_summary")
def action_vision_summary():
    """Return a human-readable summary of today's visual observations."""
    try:
        from bt7274.bt7274_perception import PerceptionManager
        pm = PerceptionManager()
        return pm.get_today_summary()
    except Exception as e:
        return f"Failed to retrieve vision summary: {str(e)}"


@register_action("vision_status")
def action_vision_status():
    """Return the current status of BT-7274's optical sensors."""
    try:
        from bt7274.bt7274_perception import PerceptionManager
        pm = PerceptionManager()
        status = pm.status()
        lines = [
            "BT-7274 Optical Sensor Status",
            "─" * 30,
            f"Camera ready: {'Yes' if status['camera_ready'] else 'No'}",
            f"Vision model: {status['vision_model']}",
            f"Model available: {'Yes' if status['vision_model_available'] else 'No'}",
            f"Observations today: {status['observations_today']}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Vision status unavailable: {str(e)}"


@register_action("analyze_that")
def action_analyze_that(pilot_query: str | None = None):
    """
    Tactical object analysis — detect, classify, and assess threat/relevance.

    Captures a frame and returns a structured tactical analysis with:
      - Object labels with confidence levels
      - Threat assessment (none/low/medium/high/critical)
      - Mission relevance (none/low/medium/high)
      - Suggested web lookups for unknown objects

    Args:
        pilot_query: The Pilot's exact words that triggered the analysis.

    Returns:
        Formatted tactical analysis string, or error message.
    """
    try:
        from bt7274.bt7274_perception import PerceptionManager
        pm = PerceptionManager()
        result = pm.analyze_that(pilot_query=pilot_query, include_web_lookup=True)
        if not result["success"]:
            return f"Optical sensors offline: {result.get('error', 'Unknown error')}"

        # Build a formatted response
        lines = [result["description"]]

        if result["objects"]:
            lines.append("")
            lines.append("OBJECT ANALYSIS:")
            for obj in result["objects"]:
                threat_icon = _threat_icon(obj["threat"])
                rel_icon = _relevance_icon(obj["relevance"])
                reason_str = f" — {obj['reason']}" if obj.get("reason") else ""
                lines.append(
                    f"  {threat_icon} {obj['label']} "
                    f"(confidence: {obj['confidence']}, "
                    f"threat: {obj['threat']}{rel_icon}){reason_str}"
                )

        if result["web_lookups"]:
            lines.append("")
            lines.append("SUGGESTED WEB LOOKUPS:")
            for lookup in result["web_lookups"]:
                lines.append(f"  • {lookup}")

        return "\n".join(lines)
    except Exception as e:
        return f"Vision system error: {str(e)}"


def _threat_icon(threat: str) -> str:
    """Return a visual icon for threat level."""
    return {
        "none": "○",
        "low": "◈",
        "medium": "◆",
        "high": "⚠",
        "critical": "☠",
    }.get(threat.lower(), "?")


def _relevance_icon(relevance: str) -> str:
    """Return a visual icon for relevance level."""
    return {
        "none": "",
        "low": "",
        "medium": " ★",
        "high": " ★★",
    }.get(relevance.lower(), "")


# ─── Calendar Actions ───────────────────────────────────────────────

@register_action("get_calendar_events")
def action_get_calendar_events():
    """Return today's calendar events from macOS Calendar.app."""
    try:
        from bt7274.bt7274_workstation.calendar_monitor import CalendarMonitor
        monitor = CalendarMonitor({"enabled": True})
        return monitor.get_today_events()
    except Exception as e:
        return f"Calendar access failed: {str(e)}"


@register_action("get_upcoming_events")
def action_get_upcoming_events(hours: int = 2):
    """Return upcoming calendar events within the next N hours."""
    try:
        from bt7274.bt7274_workstation.calendar_monitor import CalendarMonitor
        monitor = CalendarMonitor({
            "enabled": True,
            "upcoming_warning_minutes": hours * 60,
        })
        events = monitor._fetch_events()
        if not events:
            return "No upcoming events, Pilot."

        from datetime import datetime, timedelta
        now = datetime.now()
        threshold = now + timedelta(hours=hours)

        upcoming = []
        for evt in events:
            try:
                # Use the same parsing as _parse_event_datetime
                start_dt = monitor._parse_event_datetime(evt)
                if start_dt and now <= start_dt <= threshold:
                    upcoming.append(evt)
            except Exception:
                continue

        if not upcoming:
            return f"No events in the next {hours} hour{'s' if hours != 1 else ''}, Pilot."

        lines = [f"Upcoming events in the next {hours} hour{'s' if hours != 1 else ''}:"]
        for evt in upcoming:
            time_str = monitor._format_event_time(evt)
            title = evt.get("title", "Untitled")
            location = evt.get("location", "")
            loc_str = f" at {location}" if location else ""
            lines.append(f"  {time_str} — {title}{loc_str}")

        return "\n".join(lines)
    except Exception as e:
        return f"Calendar access failed: {str(e)}"


@register_action("get_calendar_range")
def action_get_calendar_range(range_name: str = "today"):
    """Return calendar events for a specific time range.

    Args:
        range_name: One of 'today', 'tomorrow', 'this_week', 'next_week',
                    'this_month', 'next_month'
    """
    try:
        from bt7274.bt7274_workstation.calendar_monitor import CalendarMonitor
        monitor = CalendarMonitor({"enabled": True})

        range_handlers = {
            "today": monitor.get_today_events,
            "tomorrow": monitor.get_tomorrow_events,
            "this_week": monitor.get_this_week_events,
            "next_week": monitor.get_next_week_events,
            "this_month": monitor.get_this_month_events,
            "next_month": monitor.get_next_month_events,
        }

        handler = range_handlers.get(range_name)
        if handler:
            return handler()
        return f"Unknown calendar range: {range_name}"
    except Exception as e:
        return f"Calendar access failed: {str(e)}"
