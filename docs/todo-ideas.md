# BT-7274 Feature Ideas & Logging Plan (with Log Paths)

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

---

## 5. VPN Cloak (Proton VPN)

When VPN connects/disconnects:

- Connect: “Cloak engaged. Network traffic obfuscated.”
- Disconnect: “Cloak offline. We are exposed, Pilot.”

Config:

- Option to auto‑connect on public Wi‑Fi.
- Ask BT to enable/disable auto‑cloak.

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

## 10. Calendar & Memory

### 10.1 Calendar Awareness

BT can:

- List today’s events.
- Warn about upcoming events.
- Include events in briefs/debriefs.

Config:

- `calendar_access: on/off`.
- Ask BT to enable/disable it.

Log it down

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
