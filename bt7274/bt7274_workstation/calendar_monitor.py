"""
Calendar Awareness for BT-7274.
Queries macOS Calendar.app via AppleScript for today's events.
Warns about upcoming events within a configurable threshold.
Logs state changes to telemetry/system and event data to telemetry/health.
"""

import json
import os
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

    # ─── AppleScript execution ────────────────────────────────────────

    def _run_applescript(self, script: str) -> tuple[bool, str]:
        """Run an AppleScript and return (success, output)."""
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=45,
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

        script = (
            'tell application "Calendar"\n'
            '    set calNames to name of every calendar\n'
            'end tell\n'
            'return "granted"'
        )
        success_flag, output = self._run_applescript(script)
        self._calendar_access_granted = success_flag and "granted" in output
        return self._calendar_access_granted

    # ─── Event fetching ───────────────────────────────────────────────

    def _fetch_events(self) -> list[dict]:
        """Fetch today's events from Calendar."""
        return self._fetch_events_range(0, 1)

    def _fetch_events_range(self, start_offset_days: int, num_days: int) -> list[dict]:
        """Fetch events from Calendar.app for a specific date range.

        Args:
            start_offset_days: Days from today to start (0 = today, 1 = tomorrow, etc.)
            num_days: Number of days to include in the range.

        Returns a list of dicts with keys:
            title, start_time, end_time, location, calendar_name, all_day, uid
        """
        if not self._check_calendar_access():
            return []

        # Build AppleScript using string concatenation to avoid f-string
        # escaping issues with AppleScript's {} record syntax
        script = (
            'tell application "Calendar"\n'
            f'    set rangeStart to ((current date) - (time of (current date))) + ({start_offset_days} * days)\n'
            f'    set rangeEnd to rangeStart + ({num_days} * days)\n'
            '    set eventList to {}\n'
            '    repeat with cal in every calendar\n'
            '        set calName to name of cal\n'
            '        try\n'
            '            set calEvents to (every event of cal whose start date >= rangeStart and start date <= rangeEnd)\n'
            '            repeat with evt in calEvents\n'
            '                set evtTitle to summary of evt\n'
            '                if evtTitle is missing value then set evtTitle to "(No title)"\n'
            '                set evtStart to start date of evt\n'
            '                set evtEnd to end date of evt\n'
            '                set evtLocation to location of evt\n'
            '                if evtLocation is missing value then set evtLocation to ""\n'
            '                set evtAllDay to allday event of evt\n'
            '                set evtUID to uid of evt\n'
            '                if evtUID is missing value then set evtUID to ""\n'
            '                set end of eventList to {title:evtTitle, start_time:evtStart as string, end_time:evtEnd as string, location:evtLocation, calendar_name:calName, all_day:evtAllDay, uid:evtUID}\n'
            '            end repeat\n'
            '        end try\n'
            '    end repeat\n'
            '    if (count of eventList) is 0 then\n'
            '        return "NO_EVENTS"\n'
            '    end if\n'
            '    set AppleScript\'s text item delimiters to "|||"\n'
            '    set outputList to {}\n'
            '    repeat with evt in eventList\n'
            '        set evtStr to title of evt & "|||" & start_time of evt & "|||" & end_time of evt & "|||" & location of evt & "|||" & calendar_name of evt & "|||" & (all_day of evt as string) & "|||" & uid of evt\n'
            '        set end of outputList to evtStr\n'
            '    end repeat\n'
            '    return outputList as string\n'
            'end tell'
        )
        success_flag, output = self._run_applescript(script)
        if not success_flag:
            error(f"Calendar fetch failed: {output}")
            return []

        if not output or output == "NO_EVENTS":
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

    def _parse_event_datetime(self, event: dict) -> Optional[datetime]:
        """Parse an event's start_time string into a datetime object.

        Handles both AppleScript format ("Sunday, May 10, 2026 at 10:00:00 AM")
        and NSDate description format ("2026-05-10 08:00:00 +0000").
        """
        start_str = event.get("start_time", "")
        if not start_str:
            return None

        # Try NSDate description format: "2026-05-10 08:00:00 +0000"
        try:
            # Strip timezone offset
            clean = start_str.rsplit(" ", 1)[0] if " +" in start_str or " -" in start_str[10:] else start_str
            return datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

        # Try AppleScript format: "Sunday, May 10, 2026 at 10:00:00 AM"
        try:
            if " at " in start_str:
                date_part, time_part = start_str.split(" at ")
                return datetime.strptime(f"{date_part} {time_part}", "%A, %B %d, %Y %I:%M:%S %p")
        except ValueError:
            pass

        return None

    def _format_event_time(self, event: dict) -> str:
        """Format an event's time for display."""
        if event.get("all_day"):
            return "All day"

        dt = self._parse_event_datetime(event)
        if dt:
            return dt.strftime("%I:%M %p").lstrip("0")

        return event.get("start_time", "")

    def _format_event_date(self, event: dict) -> str:
        """Format an event's date for multi-day views (e.g., 'Sun 10 May')."""
        dt = self._parse_event_datetime(event)
        if dt:
            return dt.strftime("%a %d %b")
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

    # ─── Time-range queries ───────────────────────────────────────────

    def _format_events_for_voice(self, events: list[dict], label: str) -> str:
        """Format a list of events into a voice-friendly string.

        For short ranges (today, tomorrow): lists each event individually.
        For longer ranges (week, month): groups events by day.
        """
        if not events:
            return f"No events {label}, Pilot."

        # Deduplicate by UID
        seen_uids = set()
        unique = []
        for e in events:
            uid = e.get("uid", "")
            if uid and uid in seen_uids:
                continue
            seen_uids.add(uid)
            unique.append(e)

        count = len(unique)

        # For short ranges (1-2 days), list individually
        if label in ("today", "tomorrow"):
            unique = unique[:self.max_events_display]
            lines = [f"You have {count} event{'s' if count != 1 else ''} {label}:"]
            for evt in unique:
                time_str = self._format_event_time(evt)
                title = evt.get("title", "Untitled")
                location = evt.get("location", "")
                cal = evt.get("calendar_name", "")
                if time_str == "All day":
                    line = f"  {title}"
                else:
                    line = f"  {time_str} — {title}"
                if location:
                    line += f" at {location}"
                if cal:
                    line += f" [{cal}]"
                lines.append(line)
            return "\n".join(lines)

        # For longer ranges, group by day
        from collections import defaultdict
        by_day = defaultdict(list)
        for evt in unique:
            date_str = self._format_event_date(evt)
            by_day[date_str].append(evt)

        # Sort days chronologically
        sorted_days = sorted(by_day.keys())

        lines = [f"You have {count} event{'s' if count != 1 else ''} {label}:"]
        for day in sorted_days:
            day_events = by_day[day]
            if len(day_events) == 1:
                evt = day_events[0]
                time_str = self._format_event_time(evt)
                title = evt.get("title", "Untitled")
                location = evt.get("location", "")
                cal = evt.get("calendar_name", "")
                if time_str == "All day":
                    line = f"  {day} — {title}"
                else:
                    line = f"  {day} {time_str} — {title}"
                if location:
                    line += f" at {location}"
                if cal:
                    line += f" [{cal}]"
                lines.append(line)
            else:
                lines.append(f"  {day}:")
                for evt in day_events:
                    time_str = self._format_event_time(evt)
                    title = evt.get("title", "Untitled")
                    location = evt.get("location", "")
                    cal = evt.get("calendar_name", "")
                    if time_str == "All day":
                        sub = f"    {title}"
                    else:
                        sub = f"    {time_str} — {title}"
                    if location:
                        sub += f" at {location}"
                    if cal:
                        sub += f" [{cal}]"
                    lines.append(sub)

        return "\n".join(lines)

    def get_tomorrow_events(self) -> str:
        """Return formatted events for tomorrow."""
        events = self._fetch_events_range(1, 1)
        return self._format_events_for_voice(events, "tomorrow")

    def get_this_week_events(self) -> str:
        """Return formatted events for the rest of this week (today through Sunday)."""
        now = datetime.now()
        # Days until Sunday (weekday 6): Monday=0, Sunday=6
        days_until_sunday = 6 - now.weekday()
        events = self._fetch_events_range(0, days_until_sunday + 1)
        return self._format_events_for_voice(events, "this week")

    def get_next_week_events(self) -> str:
        """Return formatted events for next week (Monday through Sunday)."""
        now = datetime.now()
        days_until_monday = 7 - now.weekday()
        events = self._fetch_events_range(days_until_monday, 7)
        return self._format_events_for_voice(events, "next week")

    def get_this_month_events(self) -> str:
        """Return formatted events for the rest of this month."""
        now = datetime.now()
        # Calculate days remaining in this month
        if now.month == 12:
            next_month = datetime(now.year + 1, 1, 1)
        else:
            next_month = datetime(now.year, now.month + 1, 1)
        days_remaining = (next_month - now).days
        events = self._fetch_events_range(0, days_remaining)
        return self._format_events_for_voice(events, "this month")

    def get_next_month_events(self) -> str:
        """Return formatted events for next month."""
        now = datetime.now()
        # Calculate start of next month
        if now.month == 12:
            first_of_next = datetime(now.year + 1, 1, 1)
            first_of_month_after = datetime(now.year + 1, 2, 1)
        elif now.month == 11:
            first_of_next = datetime(now.year, 12, 1)
            first_of_month_after = datetime(now.year + 1, 1, 1)
        else:
            first_of_next = datetime(now.year, now.month + 1, 1)
            first_of_month_after = datetime(now.year, now.month + 2, 1)

        days_in_next_month = (first_of_month_after - first_of_next).days
        days_until_next_month = (first_of_next - now).days
        events = self._fetch_events_range(days_until_next_month, days_in_next_month)
        return self._format_events_for_voice(events, "next month")

    def get_events_for_range(self, start_offset_days: int, num_days: int, label: str) -> str:
        """Return formatted events for an arbitrary date range."""
        events = self._fetch_events_range(start_offset_days, num_days)
        return self._format_events_for_voice(events, label)

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

            start_dt = self._parse_event_datetime(evt)
            if start_dt is None:
                continue

            if now <= start_dt <= threshold:
                upcoming.append(evt)

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
            for evt in events:
                if evt.get("uid") == uid:
                    start_dt = self._parse_event_datetime(evt)
                    if start_dt and start_dt < now:
                        to_remove.add(uid)
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
