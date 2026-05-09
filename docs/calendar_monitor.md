# BT-7274 Calendar Awareness

## Overview

Calendar Awareness gives BT-7274 access to your macOS Calendar.app. BT can list today's events, warn about upcoming appointments, and include your schedule in protocol briefs — all through voice commands.

---

## Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Calendar.app    │────▶│  CalendarMonitor │────▶│  BT-7274 TTS    │
│  (AppleScript)   │     │  (5 min interval) │     │  Voice Responses│
└──────────────────┘     └──────────────────┘     └─────────────────┘
                                  │
                                  ▼
                           ┌──────────────────┐
                           │  logs/telemetry/ │
                           │  system/         │
                           │  bt7274_system_  │
                           │  YYYY-MM-DD.log  │
                           └──────────────────┘
                                  │
                                  ▼
                           ┌──────────────────┐
                           │  logs/telemetry/ │
                           │  health/         │
                           │  calendar_events_│
                           │  YYYY-MM-DD.jsonl│
                           └──────────────────┘
```

---

## Voice Commands

| Command | Action |
|---------|--------|
| "What's on my calendar today?" | Lists today's events |
| "What's my schedule?" | Lists today's events |
| "Do I have any events today?" | Lists today's events |
| "What's coming up?" | Shows events in the next 2 hours |
| "What's my next event?" | Shows upcoming events |
| "Enable calendar access" | Starts calendar monitoring |
| "Disable calendar access" | Stops calendar monitoring |
| "Protocol brief" | Includes today's events in the brief |

---

## Configuration (`config.yaml`)

```yaml
calendar_access:
  enabled: false              # Off by default; enable via voice or config
  interval: 300               # seconds between checks (5 minutes)
  upcoming_warning_minutes: 15  # Warn about events starting within N minutes
  max_events_display: 10      # Max events to show in responses
```

### Options

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `false` | Master switch for calendar access |
| `interval` | int | `300` | Seconds between calendar checks |
| `upcoming_warning_minutes` | int | `15` | Warn about events starting within this many minutes |
| `max_events_display` | int | `10` | Maximum events to show in responses |

---

## Permissions

On first use, macOS will prompt you to grant Calendar access to `osascript` (or your terminal app). Grant permission in:

**System Settings → Privacy & Security → Calendars**

If access is denied, BT will respond: "Pilot, I cannot access your calendar. Check System Settings > Privacy > Calendars."

---

## Log Format

### System Logs (`logs/telemetry/system/bt7274_system_YYYY-MM-DD.log`)

```
[2026-05-09 10:00:00] [calendar_access] enabled
[2026-05-09 10:00:00] [calendar_access] disabled
[2026-05-09 10:00:00] [calendar_access] access_denied
```

### Health Logs (`logs/telemetry/health/calendar_events_YYYY-MM-DD.jsonl`)

```json
{
  "timestamp": "2026-05-09T10:00:00",
  "event_count": 3,
  "events": [
    {
      "title": "Standup meeting",
      "start_time": "Friday, May 9, 2026 at 10:00:00 AM",
      "end_time": "Friday, May 9, 2026 at 10:30:00 AM",
      "location": "Conference Room B",
      "calendar_name": "Work",
      "all_day": false
    }
  ]
}
```

---

## Example Interactions

### Listing today's events

> **Pilot:** "Hey BT, what's on my calendar today?"
>
> **BT-7274:** "You have 3 events today: 10:00 AM — Standup meeting at Conference Room B, 2:00 PM — Dentist appointment, 6:00 PM — Dinner with Sarah."

### Upcoming event warning

> **BT-7274:** "Upcoming event: Standup meeting at 10:00 AM — Conference Room B. Take note, Pilot."

### Protocol brief with calendar

> **Pilot:** "BT, protocol brief."
>
> **BT-7274:** "PROTOCOL BRIEF — Active tasks: 2. Completed today: 1. Total notes: 5. You have 3 events today: 10:00 AM — Standup meeting, 2:00 PM — Dentist appointment, 6:00 PM — Dinner with Sarah."

---

## Technical Notes

- Uses AppleScript to query Calendar.app — no external API keys or network calls required.
- Works entirely offline once Calendar access is granted.
- Follows the same monitor pattern as `WeatherMonitor`, `BatteryMonitor`, and `VPNMonitor`.
- Event warnings are deduplicated — each event is warned about only once per day.
- Warnings reset at midnight for a fresh day.
