# BT-7274 Feature Ideas & Logging Plan

## 1. Protocol Mode

**Command:** “BT, protocol brief.”

- Summarizes current goals, status, and suggestions (Titanfall-style protocol monologue).
- Can:
  - Create / update a **pilot to-do list**.
  - Append **notes** to a personal log.
- Config:
  - Toggle at startup or via command: `protocol_mode: on/off`.
  - Be able to ask BT to turn this setting on or off.
- Logging:
  - Log when protocol mode is enabled/disabled.
  - Log each protocol brief (timestamp + summary) in `logs/system.log`.

## 2. Combat Effectiveness Rating

- Tracks a percentage rating that increases when you complete:
  - Study sessions.
  - Gym / workout.
  - Coding sessions.
  - Other habits you decide to track.
- BT comments on changes (“Combat effectiveness has increased, Pilot.”).
- Config:
  - Toggle tracking at startup: `combat_rating: on/off`.
  - Be able to ask BT to turn this setting on or off.
- Logging:
  - Log when tracking is enabled/disabled.
  - Log each rating update (old → new value, reason) in `logs/system.log`.

## 3. Travel Intel

- When location changes significantly (e.g. new city):
  - “Pilot, we appear to be in Brussels. Points of interest within 500 meters: …”
- Optionally uses web search for nearby POIs.
- Config:
  - Ask at startup if BT should monitor travel intel: `travel_intel: on/off`.
  - Be able to ask BT to turn this setting on or off.
- Logging:
  - Log toggle changes.
  - Log each travel intel event (old location → new location, summary) in `logs/system.log`.

## 4. Environmental Warnings (Weather)

- Uses weather + location to warn about:
  - Rain / heavy rain.
  - Hail.
  - Thunderstorms.
  - Extreme temperatures (optional).
- Example line: “Heavy rain detected. Recommend you secure your equipment before deployment.”
- Config:
  - Ask at startup: `environmental_warnings: on/off`.
  - Be able to ask BT to turn this setting on or off.
- Logging:
  - Log toggle changes.
  - Log each warning (condition, location, severity) in `logs/system.log`.

## 5. VPN Cloak (Proton VPN)

- When VPN connects:
  - “Cloak engaged. Network traffic obfuscated.”
- When VPN disconnects:
  - “Cloak offline. We are exposed, Pilot.”
- BT must be able to **detect current VPN state**.
- Config:
  - Option to let BT auto-connect VPN in certain conditions (e.g. on public Wi-Fi).
  - Be able to ask BT to turn this setting on or off.
- Logging:
  - Log all VPN state changes (connect/disconnect, server, network) in `logs/system.log`.

## 6. Heart-Rate Style Monitoring (“Stress Mode”)

- Approximates stress / fatigue based on:
  - Continuous computer usage without a break.
  - Time of day and duration of session.
- Example line:
  - “Your activity duration exceeds recommended limits. I suggest a short rest, Pilot.”
- Config:
  - Adjustable thresholds (e.g. warn after 50 minutes of continuous use).
  - Toggle: `stress_monitoring: on/off`.
- Logging:
  - Log when monitoring is enabled/disabled.
  - Log each warning event (duration, app context if possible) in `logs/system.log`.

## 7. Focus / Pomodoro Mode

- Command: “BT, uphold the mission for 25 minutes.”
  - Starts a Pomodoro timer.
  - Optional short break message afterward.
- Example:
  - Start: “Objective accepted. 25-minute focus session initiated.”
  - End: “Objective complete. You upheld the mission, Pilot.”
- Config:
  - Customizable durations (focus + break).
- Logging:
  - Log each session start/stop, outcome (completed / interrupted) in `logs/system.log`.

## 8. Pilot Log (“BT, make log”)

- Command: “BT, make log: …”
  - Appends free-form text to a **personal pilot log**.
- Access:
  - BT has read/write access to a dedicated logs folder.
- Storage:
  - Append to `logs/pilot_logs/<date>.log` or a single `logs/pilot_logs/pilot_log.md`.
- Logging:
  - Each entry includes timestamp + raw text.
  - Optionally tag entries by type (mood, idea, task).

## 9. Event-Driven BT Lines (Success / Error Hooks)

- Success examples:
  - On successful web search: “Data core reinitialized. Information acquired.”
- Error examples:
  - On command failure: “That would violate Protocol 3.”
- Integration:
  - Hook into your command dispatcher so BT always reacts.
- Logging:
  - Log all **errors** and failed commands in `logs/system.log` (command + reason).
  - Optional: log major successes (e.g. long tasks completed).

---

## 10. Calendar & Memory

### 10.1 Calendar Awareness

- BT can read your calendar and:
  - List today’s events.
  - Warn about upcoming events (“Pilot, you have a briefing in 30 minutes.”).
  - Include events in protocol briefs and daily mission summaries.
- Config:
  - Toggle calendar access: `calendar_access: on/off`.
  - Be able to ask BT to turn this setting on or off.
- Logging:
  - Log when calendar access is enabled/disabled.
  - Log reminders/alerts triggered (event, time, lead time) in `logs/system.log`.

### 10.2 Memory / Long-Term State

- BT can “remember”:
  - Preferences (e.g. study times, usual locations).
  - Repeated logs (e.g. frequent stress, recurring tasks).
  - Key facts you explicitly flag: “BT, remember that X.”
- Usage:
  - Feed memory into protocol briefs, debriefs, and combat effectiveness commentary.
- Config:
  - Toggle explicit memory: `memory_store: on/off`.
- Logging:
  - Log “remember” actions (what was stored) in `logs/system.log` or `logs/pilot_logs/memory.log`.

### 10.3 Voice Link / Identity Check

- Command / ritual: “BT, link to pilot.”
- BT:
  - Records a voice embedding for you.
  - On sensitive commands (e.g. shutting down servers, opening sensitive logs), checks that the current speaker roughly matches the stored embedding.
- Config:
  - Toggle voice-check requirement for high-privilege actions: `voice_link_required: on/off`.
- Logging:
  - Log link creation/updates (no raw audio, just metadata).
  - Log allowed/denied sensitive actions with voice-check result in `logs/system.log`.

---

## 11. Camera / Vision Features

### 11.1 Object Recognition as Mission Intel

- Command: “BT, analyze that.”
  - Uses camera to detect object(s).
  - Returns:
    - Object label(s).
    - Short “threat level / relevance” line.
  - Optionally uses web search for extra context.
- Logging:
  - Log each analysis (object(s), confidence, threat level) in `logs/vision.log`.

### 11.2 Augmented HUD

- Display on laptop/phone:
  - Live camera feed with bounding boxes or overlays.
  - BT commentary (e.g. current target, warnings).
- Optional modes:
  - “Combat HUD” (only threats / people).
  - “Explorer HUD” (POIs, items).
- Config:
  - Toggle HUD modes; be able to ask BT to turn this setting on or off.
- Logging:
  - Log HUD mode changes and notable detections in `logs/vision.log`.

---

## 12. System Comments / Battery Warnings

- Battery monitoring:
  - Warns at **50%, 20%, 10%, 5%**:
    - 50%: “Pilot, reserves at 50%.”
    - 20%: “Battery at 20%. Recommend you locate a charging source.”
    - 10%, 5%: more urgent variants.
- Logging strategy:
  - Log **critical levels** only (≤ 10%), to avoid spam.
  - Optionally include whether action was taken (user plugged in, BT adjusted brightness, etc.).
- Logging:
  - `logs/system.log` entries only for 10% and 5% thresholds.

---

## 13. In-Cosplay Features

### 13.1 Suit Integrity Monitoring

- BT monitors:
  - Approximate internal temperature (via sensors if available, or time-in-suit as a proxy).
  - Time since last water break.
- Lines:
  - “Pilot, suit integrity stable.”
  - “Pilot, hydration below recommended levels. I advise you locate water.”
- Config:
  - Toggle suit monitoring when entering/exiting cosplay mode: `suit_mode: on/off`.
- Logging:
  - Log suit mode on/off.
  - Log hydration / overheating warnings in `logs/system.log` or a dedicated `logs/suit.log`.

---

## 14. Global Logging Structure (Suggested)

- `logs/system.log`
  - Feature toggles (on/off).
  - Errors and failed commands.
  - System events (VPN, battery, environmental warnings, combat rating updates, focus sessions, calendar alerts, memory actions, voice-link checks, suit warnings).
- `logs/pilot_logs/…`
  - Your personal logs created via “BT, make log.”
  - Optional dedicated `memory.log` if you separate explicit “remember” events.
- `logs/vision.log`
  - Camera detections, analyze-commands, HUD mode changes.
- `logs/suit.log` (optional)
  - Suit integrity monitoring events (time in suit, hydration/temperature warnings).

