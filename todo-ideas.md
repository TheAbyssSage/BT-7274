# BT-7274 Feature Ideas & Logging Plan (with Log Paths)

Current log folders:

- logs/bt_brief
- logs/bt_logs
- logs/bt_vision
- logs/bt_workstation
- logs/bt-pilot_interactions
- logs/pilot_health
- logs/pilot_logs
- logs/pilot_voice_commands
- logs/system_logs

---

## 1. Protocol Mode

**Command:** “BT, protocol brief.”

- Summarizes current goals, status, and suggestions.
- Can:
  - Create / update a **pilot to-do list**.
  - Append **notes** to a personal log.

Config:

- Toggle at startup or via command: `protocol_mode: on/off`.
- Ask BT to enable/disable it.

Logging:

- State changes:
  - To `logs/system_logs`
    - Example: `2025-04-28T10:12Z [protocol_mode] enabled`
- Brief content:
  - To `logs/bt_brief` (one file per day or rolling)
    - Example: `2025-04-28T10:13Z PROTOCOL BRIEF: …`

---

## 2. Combat Effectiveness Rating

Tracks a % rating that increases when you complete:

- Study sessions
- Gym / workout
- Coding sessions
- Other habits

Config:

- Toggle at startup: `combat_rating: on/off`.
- Ask BT to enable/disable it.

Logging:

- State changes:
  - To `logs/system_logs`
- Rating updates (old → new, reason):
  - To `logs/bt_logs`
    - Example:  
      `2025-04-28T11:00Z [combat_effectiveness] 72 → 76 (completed 25min focus session)`

---

## 3. Travel Intel

When location changes significantly:

- “Pilot, we appear to be in Brussels. Points of interest within 500 meters: …”

Config:

- Startup toggle: `travel_intel: on/off`.
- Ask BT to enable/disable it.

Logging:

- State changes:
  - To `logs/system_logs`
- Travel intel events:
  - To `logs/bt_logs`
    - Example:  
      `2025-04-29T08:10Z [travel_intel] Genk → Brussels, 5 POIs`

---

## 4. Environmental Warnings (Weather)

Uses weather + location to warn about:

- Rain / heavy rain
- Hail
- Thunderstorms
- Extreme temperatures

Config:

- Startup toggle: `environmental_warnings: on/off`.
- Ask BT to enable/disable it.

Logging:

- State changes:
  - To `logs/system_logs`
- Weather warnings:
  - To `logs/pilot_health` (it’s about safety/conditions for the pilot)
    - Example:  
      `2025-04-29T09:02Z [weather_warning] heavy_rain, Genk, severity=medium`

---

## 5. VPN Cloak (Proton VPN)

When VPN connects/disconnects:

- Connect: “Cloak engaged. Network traffic obfuscated.”
- Disconnect: “Cloak offline. We are exposed, Pilot.”

Config:

- Option to auto‑connect on public Wi‑Fi.
- Ask BT to enable/disable auto‑cloak.

Logging:

- All VPN state changes:
  - To `logs/system_logs`
    - Example:  
      `2025-04-28T12:00Z [vpn] connected proton-be-01 wifi=Starbucks_Guest`

---

## 6. Heart-Rate Style Monitoring (“Stress Mode”)

Approximates stress/fatigue from:

- Continuous computer usage
- Time of day + session length

Config:

- Adjustable thresholds.
- Toggle: `stress_monitoring: on/off`.

Logging:

- State changes:
  - To `logs/system_logs`
- Warnings:
  - To `logs/pilot_health`
    - Example:  
      `2025-04-28T13:30Z [stress_warning] 90min continuous use, app=VSCode`

---

## 7. Focus / Pomodoro Mode

Command: “BT, uphold the mission for 25 minutes.”

- Starts a Pomodoro timer.
- Optional break message.

Config:

- Custom focus + break durations.

Logging:

- Session start/stop/outcome:
  - To `logs/bt_workstation`
    - Example:  
      `2025-04-28T14:00Z [focus_session] start 25min task="Laravel API"`  
      `2025-04-28T14:25Z [focus_session] complete`

---

## 8. Pilot Log (“BT, make log” / BT personal logs)

Command: “BT, make log: …”

- Appends free‑form text to pilot logs.

Storage:

- BT’s own internal logs (system‑style):
  - To `logs/bt_logs/<name>_<date>.log`
- Your personal pilot logs:
  - To `logs/pilot_logs/<name>_<date>.log`
  - Or a single `logs/pilot_logs/pilot_logs.md`

Logging:

- Each entry with timestamp + raw text (and optional tags).
- No extra meta log needed beyond the file itself.

---

## 9. Event-Driven BT Lines (Success / Error Hooks)

Examples:

- Success (e.g. web search OK): “Data core reinitialized. Information acquired.”
- Error (command failure): “That would violate Protocol 3.”

Logging:

- Errors and failed commands:
  - To `logs/system_logs`
    - Example:  
      `2025-04-28T15:10Z [error] command="bt vpn on" reason="proton-cli not found"`
- Optional: major successes (long tasks, big actions):
  - Also to `logs/system_logs`

---

## 10. Calendar & Memory

### 10.1 Calendar Awareness

BT can:

- List today’s events.
- Warn about upcoming events.
- Include events in briefs/debriefs.

Config:

- `calendar_access: on/off`.
- Ask BT to enable/disable it.

Logging:

- State changes:
  - To `logs/system_logs`
- Alerts/reminders fired:
  - To `logs/bt_logs`
    - Example:  
      `2025-04-29T08:30Z [calendar_alert] "Syntra class" starts in 30min`

### 10.2 Memory / Long-Term State

BT can “remember”:

- Preferences (study times, locations).
- Repeated patterns from logs.
- Explicit facts (“BT, remember that X”).

Config:

- Toggle: `memory_store: on/off`.

Logging:

- “Remember” actions (what was stored):
  - To `logs/bt_logs`
    - Example:  
      `2025-04-28T16:00Z [memory_store] key="favorite_editor" value="VSCode"`

### 10.3 Voice Link / Identity Check

Command: “BT, link to pilot.”

- Stores a voice embedding.
- Checks identity on high‑privilege actions.

Config:

- `voice_link_required: on/off`.

Logging:

- Link creation/updates:
  - To `logs/pilot_voice_commands`
- Allowed/denied privileged commands:
  - To `logs/pilot_voice_commands`
    - Example:  
      `2025-04-28T17:10Z [voice_auth] action="shutdown_proxmox" result=denied score=0.62`

---

## 11. Camera / Vision Features

### 11.1 Object Recognition as Mission Intel

Command: “BT, analyze that.”

- Detects objects.
- Returns labels + threat/relevance.
- Optionally web‑lookups.

Logging:

- Analyses:
  - To `logs/bt_vision`
    - Example:  
      `2025-04-28T18:00Z [vision_analyze] object="stairs" conf=0.88 threat=low`

### 11.2 Augmented HUD

- Live feed with overlays + commentary.
- Modes:
  - “Combat HUD”
  - “Explorer HUD”

Config:

- Toggle HUD on/off and switch modes.

Logging:

- HUD mode changes + notable detections:
  - To `logs/bt_vision`
    - Example:  
      `2025-04-28T18:05Z [hud_mode] mode="combat"`

---

## 12. System Comments / Battery Warnings

Battery monitoring:

- Warn at 50%, 20%, 10%, 5%.

Logging:

- Only **critical levels** (≤ 10%):
  - To `logs/system_logs`
    - Example:  
      `2025-04-28T19:00Z [battery] level=10%`

---

## 13. In-Cosplay Features

### 13.1 Suit Integrity Monitoring

BT monitors:

- Approx. internal temp (sensor or time‑in‑suit).
- Time since last water break.

Lines:

- “Pilot, suit integrity stable.”
- “Pilot, hydration below recommended levels. I advise you locate water.”

Config:

- `suit_mode: on/off` when entering/exiting cosplay.

Logging:

- Suit mode on/off:
  - To `logs/system_logs`
- Suit‑specific warnings and metrics:
  - To `logs/system_logs`  
    or, if you want separation, create & use `logs/suit.log` later.

---

## 14. Interaction Meta (Optional)

You already have `logs/bt-pilot_interactions`:

- Use it as a **high‑level conversation timeline** between you and BT:
  - One file per day with:
    - Commands issued.
    - Short summaries of BT’s replies.
    - Pointers to detailed logs (e.g. “see bt_workstation for session details”).

Example entry in `logs/bt-pilot_interactions`:

- `2025-04-28T20:00Z [interaction] "BT, uphold the mission for 25 minutes." → focus_session started (see bt_workstation)`
