"""
Calendar Awareness for BT-7274.
Queries macOS Calendar.app via AppleScript for today's events.
Warns about upcoming events within a configurable threshold.
Logs state changes to telemetry/system and event data to telemetry/health.
"""

import json
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from bt7274.bt7274_assistant.ui import info, success, warning, error, status
from bt7274.bt7274_workstation.log_manager import (
    get_telemetry_system_dir,
    get_telemetry_health_dir,
    append_log,
    append_jsonl,
    daily_log_path,
    daily_jsonl_path,
)


class CalendarMonitor:
    """Monitors macOS Calendar.app and surfaces events to BT-7274."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", False)
        self.interval = self.config.get("interval", 300)  # seconds (5 min default)
        self.upcoming_warning_minutes = self.config.get("upcoming_warning_minutes", 15)
        self.max_events_display = self.config.get("max_events_display", 10)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_events: list[dict] = []
        self._warned_event_ids: set[str] = set()
        self._calendar_access_granted: Optional[bool] = None

        # Log directories
        self._system_log_dir = get_telemetry_system_dir()
        self._health_log_dir = get_telemetry_health_dir()
        self._system_log_dir.mkdir(parents=True, exist_ok=True)
        self._health_log_dir.mkdir(parents=True, exist_ok=True)

    # ─── AppleScript queries ──────────────────────────────────────────

    def _run_applescript(self, script: str) -> tuple[bool, str]:
        """Run an AppleScript and return (success, output)."""
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                return False, result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "AppleScript timed out"
        except FileNotFoundError:
            return False, "osascript not available"
        except Exception as e:
            return False, str(e)

    def _check_calendar_access(self) -> bool:
        """Check if Calendar.app access is granted."""
        if self._calendar_access_granted is not None:
            return self._calendar_access_granted

        script = '''
        try
            tell application "Calendar"
                set calNames to name of every calendar
            end tell
            return "granted"
        on error errMsg
            return "denied: " & errMsg
        end try
        '''
        success_flag, output = self._run_applescript(script)
        self._calendar_access_granted = success_flag and output.startswith("granted")
        return self._calendar_access_granted

    def _fetch_events(self) -> list[dict]:
        """Fetch today's and upcoming events from Calendar.app.

        Returns a list of dicts with keys:
            title, start_time, end_time, location, calendar_name, all_day, uid
        """
        if not self._check_calendar_access():
            return []

        # Fetch events for today + upcoming_warning_minutes buffer
        script = f'''
        tell application "Calendar"
            set todayStart to (current date) - (time of (current date))
            set todayEnd to todayStart + (24 * hours) + ({self.upcoming_warning_minutes} * minutes)
            
            set eventList to {{}}
            repeat with cal in every calendar
                set calName to name of cal
                try
                    set calEvents to (every event of cal whose start date >= todayStart and start date <= todayEnd)
                    repeat with evt in calEvents
                        set evtTitle to summary of evt
                        if evtTitle is missing value then set evtTitle to "(No title)"
                        set evtStart to start date of evt
                        set evtEnd to end date of evt
                        set evtLocation to location of evt
                        if evtLocation is missing value then set evtLocation to ""
                        set evtAllDay to allday event of evt
                        set evtUID to uid of evt
                        if evtUID is missing value then set evtUID to ""
                        
                        set end of eventList to {{
                            title:evtTitle,
                            start_time:evtStart as string,
                            end_time:evtEnd as string,
                            location:evtLocation,
                            calendar_name:calName,
                            all_day:evtAllDay,
                            uid:evtUID
                        }}
                    end repeat
                end try
            end repeat
            
            -- Sort by start time
            set AppleScript's text item delimiters to "|||"
            set outputList to {{}}
            repeat with evt in eventList
                set evtStr to title of evt & "|||" & start_time of evt & "|||" & end_time of evt & "|||" & location of evt & "|||" & calendar_name of evt & "|||" & (all_day of evt as string) & "|||" & uid of evt
                set end of outputList to evtStr
            end repeat
            
            return outputList as string
        end tell
        '''
        success_flag, output = self._run_applescript(script)
        if not success_flag:
            error(f"Calendar fetch failed: {output}")
            return []

        if not output:
            return []

        events = []
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("|||")
            if len(parts) >= 7:
                try:
                    events.append({
                        "title": parts[0].strip(),
                        "start_time": parts[1].strip(),
                        "end_time": parts[2].strip(),
                        "location": parts[3].strip(),
                        "calendar_name": parts[4].strip(),
                        "all_day": parts[5].strip().lower() == "true",
                        "uid": parts[6].strip(),
                    })
                except (IndexError, ValueError):
                    continue

        # Sort by start_time
        events.sort(key=lambda e: e.get("start_time", ""))

        return events

    # ─── Event formatting ─────────────────────────────────────────────

    def _format_event_time(self, event: dict) -> str:
        """Format an event's time for display."""
        if event.get("all_day"):
            return "All day"

        try:
            start_str = event.get("start_time", "")
            # AppleScript returns dates like "Friday, May 9, 2026 at 10:00:00 AM"
            # Try to parse and extract just the time
            if " at " in start_str:
                time_part = start_str.split(" at ")[1]
                # Strip seconds: "10:00:00 AM" -> "10:00 AM"
                parts = time_part.split(":")
                if len(parts) >= 2:
                    ampm = parts[-1].split(" ")[-1] if " " in parts[-1] else ""
                    return f"{parts[0]}:{parts[1]} {ampm}".strip()
            return start_str
        except Exception:
            return event.get("start_time", "")

    def _format_event_for_llm(self, event: dict) -> str:
        """Format a single event compactly for LLM consumption."""
        time_str = self._format_event_time(event)
        title = event.get("title", "Untitled")
        location = event.get("location", "")
        cal = event.get("calendar_name", "")

        parts = [f"{time_str} - {title}"]
        if location:
            parts.append(f"({location})")
        if cal:
            parts.append(f"[{cal}]")
        return " ".join(parts)

    def get_today_events(self) -> str:
        """Return a formatted string of today's events for voice response."""
        events = self._fetch_events()
        self._last_events = events

        if not events:
            return "No events scheduled for today, Pilot."

        today_events = [e for e in events if not e.get("all_day") or True]
        today_events = today_events[:self.max_events_display]

        lines = [f"You have {len(events)} event{'s' if len(events) != 1 else ''} today:"]
        for evt in today_events:
            time_str = self._format_event_time(evt)
            title = evt.get("title", "Untitled")
            location = evt.get("location", "")
            loc_str = f" at {location}" if location else ""
            lines.append(f"  {time_str} — {title}{loc_str}")

        return "\n".join(lines)

    def get_events_for_llm(self) -> str:
        """Return a compact string of events for LLM context injection."""
        events = self._fetch_events()
        self._last_events = events

        if not events:
            return "No events today."

        formatted = [self._format_event_for_llm(e) for e in events[:self.max_events_display]]
        return "Today's events: " + "; ".join(formatted)

    def get_upcoming_warnings(self) -> list[dict]:
        """Return events starting within upcoming_warning_minutes that haven't been warned about."""
        events = self._fetch_events()
        self._last_events = events

        now = datetime.now()
        threshold = now + timedelta(minutes=self.upcoming_warning_minutes)
        upcoming = []

        for evt in events:
            uid = evt.get("uid", "")
            if uid in self._warned_event_ids:
                continue

            try:
                start_str = evt.get("start_time", "")
                # Parse AppleScript date format
                # "Friday, May 9, 2026 at 10:00:00 AM"
                if " at " in start_str:
                    date_part, time_part = start_str.split(" at ")
                    # Parse date: "Friday, May 9, 2026"
                    # Parse time: "10:00:00 AM"
                    from datetime import datetime as dt
                    try:
                        start_dt = dt.strptime(f"{date_part} {time_part}", "%A, %B %d, %Y %I:%M:%S %p")
                    except ValueError:
                        continue
                else:
                    continue

                if now <= start_dt <= threshold:
                    upcoming.append(evt)
            except Exception:
                continue

        return upcoming

    # ─── Logging ──────────────────────────────────────────────────────

    def _log_state_change(self, state: str):
        """Log state changes to telemetry/system (per-day)."""
        log_file = daily_log_path(self._system_log_dir, "bt7274_system")
        append_log(log_file, f"[calendar_access] {state}")

    def _log_event_snapshot(self, events: list[dict]):
        """Log event data to telemetry/health (per-day JSONL)."""
        log_file = daily_jsonl_path(self._health_log_dir, "calendar_events")
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_count": len(events),
            "events": [
                {
                    "title": e.get("title"),
                    "start_time": e.get("start_time"),
                    "end_time": e.get("end_time"),
                    "location": e.get("location"),
                    "calendar_name": e.get("calendar_name"),
                    "all_day": e.get("all_day"),
                }
                for e in events[:self.max_events_display]
            ],
        }
        append_jsonl(log_file, entry)

    def _warn(self, message: str, severity: str = "medium"):
        """Issue a calendar warning to the UI."""
        if severity in ("critical", "high"):
            warning(f"CALENDAR ALERT: {message}")
        else:
            info(f"CALENDAR: {message}")

    # ─── Monitor lifecycle ────────────────────────────────────────────

    def check(self) -> Optional[list[dict]]:
        """Perform a single calendar check and warn about upcoming events."""
        if not self.enabled:
            return None

        events = self._fetch_events()
        self._last_events = events

        # Log event snapshot periodically
        self._log_event_snapshot(events)

        # Check for upcoming event warnings
        upcoming = self.get_upcoming_warnings()
        for evt in upcoming:
            uid = evt.get("uid", "")
            title = evt.get("title", "Untitled")
            time_str = self._format_event_time(evt)
            location = evt.get("location", "")

            msg = f"Upcoming event: {title} at {time_str}"
            if location:
                msg += f" — {location}"
            msg += ". Take note, Pilot."

            self._warn(msg, "medium")
            self._warned_event_ids.add(uid)

        # Clean up warned IDs for events that have passed
        now = datetime.now()
        to_remove = set()
        for uid in self._warned_event_ids:
            # Find the event in last_events
            for evt in events:
                if evt.get("uid") == uid:
                    try:
                        start_str = evt.get("start_time", "")
                        if " at " in start_str:
                            date_part, time_part = start_str.split(" at ")
                            from datetime import datetime as dt
                            start_dt = dt.strptime(f"{date_part} {time_part}", "%A, %B %d, %Y %I:%M:%S %p")
                            if start_dt < now:
                                to_remove.add(uid)
                    except Exception:
                        pass
                    break
        self._warned_event_ids -= to_remove

        return events

    def reset_warnings(self):
        """Reset all warned event IDs (e.g., on new day)."""
        self._warned_event_ids.clear()

    def _monitor_loop(self):
        """Background monitoring loop."""
        last_day = datetime.now().day
        while self._running:
            # Reset warnings at midnight for a new day
            now = datetime.now()
            if now.day != last_day:
                self.reset_warnings()
                last_day = now.day

            self.check()
            time.sleep(self.interval)

    def start(self):
        """Start background calendar monitoring."""
        if not self.enabled:
            info("Calendar access disabled.")
            return
        if self._running:
            return

        # Check access on start
        if not self._check_calendar_access():
            warning("Calendar access not granted. Grant permission in System Settings > Privacy > Calendars.")
            self._log_state_change("access_denied")
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        self._log_state_change("enabled")
        status("CAL", "Calendar monitoring active")

    def stop(self):
        """Stop background calendar monitoring."""
        if self._running:
            self._log_state_change("disabled")
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def get_status(self) -> dict:
        """Return current calendar monitor status."""
        return {
            "enabled": self.enabled,
            "running": self._running,
            "access_granted": self._calendar_access_granted,
            "last_event_count": len(self._last_events),
            "upcoming_warning_minutes": self.upcoming_warning_minutes,
        }
