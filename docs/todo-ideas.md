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

---

## 15. Protocol Directive System

BT operates under three core protocols. Surface them as actual runtime states:

- **Protocol 1: Link to Pilot** — Voice auth, trust bonding, identity verification.
- **Protocol 2: Uphold the Mission** — Focus mode, task tracking, mission completion.
- **Protocol 3: Protect the Pilot** — Health warnings, stress alerts, suit integrity.

**Behavior:**
- On startup, BT announces which protocol is active based on context.
- If stress is high + task is active: *"Protocol 2 and 3 are currently in conflict, Pilot. Recommend pause."*

**Config:**
- `protocol_directives: on/off`
- `protocol_conflict_warnings: on/off`

**Logging:**
- Protocol state changes → `logs/system_logs`
- Conflicts → `logs/pilot_health`
  - Example:  
    `2026-05-11T09:00Z [protocol] active=Protocol_2 mission="Code Review" conflict=Protocol_3 stress=high`

---

## 16. Mission Board (Task System with Military Flavor)

Replaces standard todo lists with a **Mission Board**.

**Features:**
- `BT, add mission: Deploy Laravel API by 1400 hours.`
- Missions have:
  - Objective (title)
  - ETA / deadline
  - Priority: `Trivial | Standard | Critical`
  - Status: `Pending | Active | Complete | Failed`
- BT gives briefings: *"You have 3 active missions, Pilot. One is Critical."*
- On completion: *"Mission accomplished. Good work, Pilot."*
- On failure (deadline passed): *"Mission failed. We'll get them next time."*

**Config:**
- `mission_board: on/off`
- `mission_reminders: on/off` (nag before deadline)
- `mission_briefing_interval: hourly|startup|on_demand`

**Logging:**
- Mission lifecycle → `logs/bt_workstation`
  - Example:  
    `2026-05-11T10:00Z [mission] id=3 status=started priority=Critical objective="Fix production bug"`

---

## 17. Pilot Loadout / Gear Tracker

For cosplay or daily carry tracking.

**Features:**
- Log what gear you have on you or packed.
- `BT, log loadout: Titanfall helmet, jump kit, sidearm prop.`
- Before leaving: *"Pilot, loadout check: helmet confirmed. Jump kit confirmed. Sidearm confirmed. You are cleared for deployment."*
- If something missing: *"Pilot, jump kit is not logged. Confirm status."*

**Config:**
- `loadout_reminder: on/off`
- `loadout_check_trigger: location_change|time|manual`

**Logging:**
- Loadout changes → `logs/system_logs`
  - Example:  
    `2026-05-11T08:00Z [loadout] added="jump_kit" removed="sidearm_prop"`

---

## 18. Threat Assessment / Screen Analysis

Use vision or screen capture to classify what the Pilot is looking at.

**Features:**
- Detect if you're on social media vs. coding vs. gaming.
- "Threat level" is tongue-in-cheek: Twitter = High Distraction Threat.
- *"Pilot, I am detecting a high concentration of distraction vectors on your display. Recommend focus fire."*
- Integrates with Focus Mode to auto-suggest Pomodoro if "threat" persists.

**Config:**
- `threat_assessment: on/off`
- `threat_auto_focus_suggestion: on/off`

**Logging:**
- Assessments → `logs/bt_vision`
  - Example:  
    `2026-05-11T11:30Z [threat_assess] app=VSCode threat=low confidence=0.91`

---

## 19. Posture & Ergonomics Monitor ("Chassis Alignment")

Stress mode extension focused on physical ergonomics.

**Features:**
- Uses camera (or just time-based heuristics) to remind you to sit straight.
- *"Pilot, your chassis alignment appears suboptimal. Adjust posture."*
- Break reminders: *"You have been in the cockpit for 90 minutes. Stand and stretch, Pilot."*

**Config:**
- `chassis_alignment_monitor: on/off`
- `break_interval_minutes: 55`
- `camera_posture_check: on/off` (if camera available)

**Logging:**
- Warnings → `logs/pilot_health`
  - Example:  
    `2026-05-11T12:00Z [posture_warning] duration=90min action=stretch_recommended`

---

## 20. Environmental Sensors (Sound & Light)

Use microphone and camera to assess ambient conditions.

**Features:**
- **Ambient Noise:** If too loud, BT warns: *"Pilot, ambient noise levels are elevated. Voice recognition may be degraded."*
- **Lighting:** If room is too dark: *"Pilot, cockpit illumination is low. Recommend increasing brightness for eye strain reduction."*

**Config:**
- `environmental_monitoring: on/off`
- `noise_threshold_db: 65`
- `light_threshold_lux: 30`

**Logging:**
- Sensor readings → `logs/telemetry/`
  - Example:  
    `2026-05-11T13:00Z [environment] noise=72db light=20lux warning=low_light`

---

## 21. Daily Intel Briefing

BT acts as a morning briefing officer.

**Features:**
- On first interaction of the day (or at a set time):
  - Weather summary
  - Calendar overview
  - Active missions
  - Combat effectiveness rating
  - VPN status
- *"Good morning, Pilot. Here is your sitrep..."*

**Config:**
- `daily_briefing: on/off`
- `briefing_time: 08:00`
- `briefing_components: weather,calendar,missions,combat_rating,vpn`

**Logging:**
- Briefings delivered → `logs/bt-pilot_interactions`
  - Example:  
    `2026-05-11T08:00Z [daily_brief] components=weather,calendar,missions`

---

## 22. After-Action Report (End-of-Day Summary)

Mirror of the briefing — a shutdown/debrief log.

**Features:**
- On command `BT, generate AAR.` or auto at shutdown:
  - Missions completed/failed
  - Focus sessions
  - Combat rating changes
  - Health warnings issued
  - Locations visited
- Saved as a markdown file in `logs/archive/aar/`

**Config:**
- `auto_aar: on/off`
- `aar_time: 22:00`

**Logging:**
- AAR generation → `logs/system_logs`
  - Example:  
    `2026-05-11T22:00Z [aar] missions=3 completed=2 failed=1 focus_sessions=2`

---

## 23. Dropzone / Fast Travel Logger

Log significant location changes with context.

**Features:**
- When you arrive at a new city or coordinates:
  - *"Pilot, we have entered a new AO. Logging dropzone."*
  - Auto-log weather, time, and any calendar events tied to that location.
- View travel history: `BT, show dropzones.`

**Config:**
- `dropzone_logging: on/off`
- `dropzone_radius_km: 5`

**Logging:**
- Dropzones → `logs/telemetry/dropzones.log`
  - Example:  
    `2026-05-11T09:30Z [dropzone] from="Genk" to="Brussels" method=car weather=overcast_14C`

---

## 24. Enemy Classification (Vision Enhancement)

Extend YOLO detection with "lore" labels.

**Features:**
- Detected objects get Titanfall-themed classifications:
  - Person → "Pilot" or "Grunt"
  - Car → "Titan Drop Ship" or "Spectre"
  - Dog → "Alien Wildlife"
- HUD overlay shows these labels instead of standard COCO classes.

**Config:**
- `enemy_classification: on/off`
- `classification_mode: serious|humorous`

**Logging:**
- Detections → `logs/bt_vision`
  - Example:  
    `2026-05-11T14:00Z [vision] detected="grunt" actual="person" confidence=0.88`

---

## 25. Titan OS Boot Sequence & Diagnostics

Aesthetic startup experience.

**Features:**
- On launch, BT prints a fake "Titan OS" boot log to terminal:
  - `Initializing neural link...`
  - `Loading combat subroutines...`
  - `Vanguard-class chassis online.`
- Optional ASCII art of BT-7274.
- Diagnostics mode: `BT, run diagnostics.` — checks all subsystems and reports health.

**Config:**
- `boot_sequence: on/off`
- `diagnostics_on_startup: on/off`

**Logging:**
- Boot events → `logs/system_logs`
  - Example:  
    `2026-05-11T08:00Z [boot] sequence=complete subsystems=9 status=online`

---

## 26. Trust Factor / Bond Level

Gamified relationship metric between Pilot and BT.

**Features:**
- Increases with:
  - Successful voice auth
  - Completed missions
  - Positive interactions
- Decreases with:
  - Failed auth
  - Ignored warnings
  - Mission failures
- At high trust: BT uses more casual/loyal dialogue.
  - *"I trust your judgment, Pilot."*
- At low trust: More formal/rigid.
  - *"Pilot, please confirm that command."*

**Config:**
- `trust_system: on/off`
- `trust_dialogue_scaling: on/off`

**Logging:**
- Trust changes → `logs/bt-pilot_interactions`
  - Example:  
    `2026-05-11T15:00Z [trust] level=4 change=+1 reason="mission_completed"`

---

## 27. Emergency Ejection (Panic Button)

A physical or voice-activated "eject" command.

**Features:**
- Voice: `BT, eject!` or hotkey.
- Actions:
  - Kill all distracting apps (browsers, games).
  - Open focus mode immediately.
  - Play alert sound.
  - Log panic event.
- *"Ejecting! Cockpit sealed. Focus mode engaged, Pilot."*

**Config:**
- `eject_command: on/off`
- `eject_actions: kill_distractions,focus_mode,log_event`

**Logging:**
- Eject events → `logs/pilot_health`
  - Example:  
    `2026-05-11T16:00Z [eject] triggered=voice actions=3 reason="pilot_initiated"`

---

## 28. Multi-Pilot Support (Guest Mode)

Allow others to interact without polluting your logs.

**Features:**
- `BT, guest pilot entering the cockpit.`
- BT switches to generic responses.
- Logs go to separate `logs/guest_pilot/` directory.
- `BT, guest pilot departing.` — back to primary pilot.

**Config:**
- `guest_mode: on/off`
- `guest_voice_auth: on/off`

**Logging:**
- Guest sessions → `logs/guest_pilot/`
  - Example:  
    `2026-05-11T17:00Z [guest] session_start duration=15min`

---

## 29. Weapon Systems (Humorous App Launcher)

Map apps to "weapons."

**Features:**
- `BT, equip smart pistol.` → Open VS Code.
- `BT, equip charge rifle.` → Open terminal.
- `BT, equip arc grenade.` → Open music player.
- `BT, fire.` → Launch the equipped app.

**Config:**
- `weapon_system: on/off`
- Custom mappings in `config.yaml`.

**Logging:**
- Equip/fire events → `logs/bt_workstation`
  - Example:  
    `2026-05-11T18:00Z [weapon] equip="smart_pistol" app="VSCode"`

---

## 30. Long-Term Memory / Pilot Journal

BT keeps a running narrative of your journey.

**Features:**
- After significant events (travel, completed projects, cosplay events), BT offers to log a journal entry.
- Stored in `logs/pilot_memory/journal.md`.
- Can query later: `BT, what happened on May 4th?`

**Config:**
- `pilot_journal: on/off`
- `journal_prompt_events: mission_complete,travel,cosplay`

**Logging:**
- Entries → `logs/pilot_memory/journal.md`
  - Example:  
    `2026-05-11T19:00Z [journal] entry="Completed Titanfall helmet paint job. Combat rating +5."`
