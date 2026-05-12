"""
Calendar Awareness for BT-7274.
Queries macOS Calendar via EventKit (PyObjC) — no AppleScript, no Calendar.app launch.
Warns about upcoming events within a configurable threshold.
Logs state changes to telemetry/system and event data to telemetry/health.
"""

import threading
import time
from collections import defaultdict
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
    """Monitors macOS Calendar via EventKit and surfaces events to BT-7274."""

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
        self._event_store = None  # Lazy-loaded EKEventStore

        # Log directories
        self._system_log_dir = get_telemetry_system_dir()
        self._health_log_dir = get_telemetry_health_dir()
        self._system_log_dir.mkdir(parents=True, exist_ok=True)
        self._health_log_dir.mkdir(parents=True, exist_ok=True)

    # ─── EventKit access ──────────────────────────────────────────────

    def _get_event_store(self):
        """Lazy-load the EKEventStore singleton."""
        if self._event_store is None:
            try:
                import EventKit  # type: ignore
                self._event_store = EventKit.EKEventStore.alloc().init()  # type: ignore
            except Exception as e:
                warning(f"EventKit not available: {e}")
                return None
        return self._event_store

    def _check_calendar_access(self) -> bool:
        """Check if Calendar access is granted via EventKit."""
        if self._calendar_access_granted is not None:
            return self._calendar_access_granted

        store = self._get_event_store()
        if store is None:
            self._calendar_access_granted = False
            return False

        try:
            import EventKit  # type: ignore
            auth_status = EventKit.EKEventStore.authorizationStatusForEntityType_(  # type: ignore
                EventKit.EKEntityTypeEvent  # type: ignore
            )
            # 0 = NotDetermined, 1 = Restricted, 2 = Denied, 3 = Authorized
            if auth_status == 3:  # Authorized
                self._calendar_access_granted = True
            elif auth_status == 0:  # NotDetermined
                # Request access synchronously on first check
                granted = [False]
                lock = threading.Event()

                def completion(g, _err):
                    granted[0] = g
                    lock.set()

                store.requestAccessToEntityType_completion_(  # type: ignore
                    EventKit.EKEntityTypeEvent, completion  # type: ignore
                )
                lock.wait(timeout=10)
                self._calendar_access_granted = granted[0]
            else:
                self._calendar_access_granted = False
        except Exception as e:
            warning(f"Calendar access check failed: {e}")
            self._calendar_access_granted = False

        return self._calendar_access_granted

    # ─── Event fetching ───────────────────────────────────────────────

    def _fetch_events(self) -> list[dict]:
        """Fetch today's events from Calendar."""
        return self._fetch_events_range(0, 1)

    def _fetch_events_range(self, start_offset_days: int, num_days: int) -> list[dict]:
        """Fetch events from Calendar for a specific date range via EventKit.

        Args:
            start_offset_days: Days from today to start (0 = today, 1 = tomorrow, etc.)
            num_days: Number of days to include in the range.

        Returns a list of dicts with keys:
            title, start_time, end_time, location, calendar_name, all_day, uid
        """
        if not self._check_calendar_access():
            return []

        store = self._get_event_store()
        if store is None:
            return []

        try:
            import EventKit  # type: ignore
            from Foundation import NSDateComponents, NSCalendar  # type: ignore

            # Build date range using NSDateComponents for reliability
            now = datetime.now()
            cal = NSCalendar.currentCalendar()

            # Start of range: midnight + offset days
            start_comps = NSDateComponents.alloc().init()
            start_comps.setYear_(now.year)
            start_comps.setMonth_(now.month)
            start_comps.setDay_(now.day + start_offset_days)
            start_comps.setHour_(0)
            start_comps.setMinute_(0)
            start_comps.setSecond_(0)
            range_start = cal.dateFromComponents_(start_comps)

            # End of range: start + num_days
            end_comps = NSDateComponents.alloc().init()
            end_comps.setYear_(now.year)
            end_comps.setMonth_(now.month)
            end_comps.setDay_(now.day + start_offset_days + num_days)
            end_comps.setHour_(0)
            end_comps.setMinute_(0)
            end_comps.setSecond_(0)
            range_end = cal.dateFromComponents_(end_comps)

            # Build predicate and fetch
            predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
                range_start, range_end, None  # None = all calendars
            )
            ek_events = store.eventsMatchingPredicate_(predicate)

            if not ek_events:
                return []

            # Sort by start date
            ek_events = sorted(ek_events, key=lambda e: e.startDate())

            events = []
            for evt in ek_events:
                try:
                    title = evt.title() or "(No title)"
                    is_all_day = evt.isAllDay()

                    # Convert NSDate to Python datetime
                    start_ts = evt.startDate().timeIntervalSince1970()
                    end_ts = evt.endDate().timeIntervalSince1970()
                    start_dt = datetime.fromtimestamp(start_ts)
                    end_dt = datetime.fromtimestamp(end_ts)

                    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
                    end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

                    location = evt.location() or ""
                    calendar_name = evt.calendar().title() if evt.calendar() else ""
                    uid = evt.eventIdentifier() or ""

                    events.append({
                        "title": title,
                        "start_time": start_str,
                        "end_time": end_str,
                        "location": location,
                        "calendar_name": calendar_name,
                        "all_day": is_all_day,
                        "uid": uid,
                    })
                except Exception:
                    continue

            return events

        except Exception as e:
            error(f"Calendar fetch failed: {e}")
            return []

    # ─── Event formatting ─────────────────────────────────────────────

    def _parse_event_datetime(self, event: dict) -> Optional[datetime]:
        """Parse an event's start_time string into a datetime object.

        Handles ISO format from EventKit: "2026-05-10 08:00:00"
        Also handles legacy AppleScript format for backward compatibility.
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
        """Start background calendar monitoring.
        
        Returns:
            True if monitoring started successfully, False if access denied or disabled.
        """
        if not self.enabled:
            info("Calendar access disabled.")
            return False
        if self._running:
            return True

        # Check access on start
        if not self._check_calendar_access():
            warning("Calendar access not granted. Grant permission in System Settings > Privacy > Calendars.")
            self._log_state_change("access_denied")
            return False

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        self._log_state_change("enabled")
        status("CAL", "Calendar monitoring active")
        return True

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
