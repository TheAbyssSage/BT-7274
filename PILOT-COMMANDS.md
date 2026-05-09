# BT-7274 Pilot Command Reference

> **Wake Word:** Say any of the trigger phrases below to activate BT-7274 before giving a command.  
> **Console Chat Mode:** Run `./scripts/start_bt7274.sh` and select option 2 for text-only mode.

---

## Wake Words (Activation Phrases)

Say any of these to get BT's attention:

- `Hey BT`
- `BT`
- `BT 7274` / `BT-7274`
- `Hey BT-7274` / `Hey BT 7274`
- `B.T.` / `B,T.` / `B T`
- `Beatee`

---

## Information & Status Queries

| Command | What It Does |
|---------|-------------|
| `BT, what's the weather?` | Current weather at your location. |
| `BT, weather in [city]` | Weather for a specific location. |
| `BT, what's the temperature?` / `Temperature in [city]` | Current temperature. |
| `BT, what's the forecast?` | Upcoming weather forecast (3 days). |
| `BT, forecast for [city]` | Forecast for a specific location. |
| `BT, what's the weather? (raw)` | Current weather (full data dump). |
| `BT, what's the forecast? (raw)` | Forecast (full data dump). |
| `BT, what time is it?` / `What is the time?` / `Current time` | Current time. |
| `BT, what's the date?` / `What day is it?` / `Today's date` / `The date today` | Current date and day. |
| `BT, where am I?` / `What's my location?` / `Find my location` | Your current geographic location. |
| `BT, what's your status?` / `How are you doing?` / `Status report` / `Systems check` / `Systems status` / `Are you operational?` / `Are you okay?` / `Condition report` | BT's systems status report (uses original voice clips). |
| `BT, search for [topic]` | Web search with BT summarizing results. |
| `BT, who won [event]?` | Real-time info lookup via web search. |
| `BT, tell me about [topic]` | General knowledge search. |
| `BT, what's the latest news?` / `Latest news` / `Breaking news` | News summary from web search. |
| `BT, look up [query]` / `Find [query]` | Web search for any topic. |
| `BT, when is [event]?` / `How much is [thing]?` | Real-time info via web search. |

---

## Battery & Power

| Command | What It Does |
|---------|-------------|
| `BT, what's your battery?` / `Battery status` / `Power level` | Reports current battery percentage. |

> **Automatic warnings:** BT monitors battery in the background and warns at 50%, 20%, 10%, and 5%.

---

## Calendar & Schedule

| Command | What It Does |
|---------|-------------|
| `BT, what do I have today?` / `What's on today?` | Lists today's calendar events. |
| `BT, what's my schedule?` / `What do I have scheduled?` / `My schedule` / `My agenda` | Shows upcoming calendar events. |
| `BT, upcoming events` / `What's next?` / `What is next?` / `Next event` / `What's coming up?` | Shows the next event on your calendar. |
| `BT, enable calendar access` / `Turn on calendar access` | Grants BT access to your macOS Calendar. |
| `BT, disable calendar access` / `Turn off calendar access` | Revokes BT's calendar access. |

> **Note:** Calendar integration uses macOS Calendar.app via AppleScript. Grant permission in System Settings > Privacy > Calendars if prompted.

---

## Vision & Optical Sensors

| Command | What It Does |
|---------|-------------|
| `BT, what do you see?` / `Look around` / `Look at this` / `Look here` / `Take a look` / `Have a look` | Captures a frame and describes the scene. |
| `BT, scan the room` / `Scan the area` / `Scan environment` / `Optical scan` / `Visual scan` | Scans the environment and describes it. |
| `BT, describe your surroundings` / `Tell me what you see` / `Show me what you see` | Detailed scene description. |
| `BT, do you see anything?` / `Can you see anything?` | Checks for visible objects. |
| `BT, analyze that` / `Analyze this` | Tactical object analysis — detects objects with threat & relevance ratings. |
| `BT, scan that` / `Scan this object` | Same as analyze — identifies and assesses objects. |
| `BT, identify that` / `What is that?` / `Identify objects` / `Recognize this` | Identifies a specific object in view. |
| `BT, tactical analysis` | Full tactical breakdown of the visual field. |
| `BT, what are these?` / `What are those?` | Identifies multiple objects in view. |
| `BT, read this` / `Read the screen` / `Read the text` | Reads text visible in the camera frame. |
| `BT, vision summary` / `Vision log` / `What did you see?` / `What have you seen?` / `Recent sightings` | Summary of today's visual observations. |
| `BT, vision status` / `Optical log` / `Camera log` / `Sight log` | Status of BT's optical sensor subsystem. |

> **Tactical Analysis** returns: object labels with confidence levels, threat assessment (none→critical), mission relevance (none→high), and suggested web lookups for unknown objects.

---

## HUD (Heads-Up Display)

| Command | What It Does |
|---------|-------------|
| `BT, open HUD` / `Show HUD` / `Pilot HUD` / `Activate HUD` / `Display HUD` / `Launch HUD` / `Bring up HUD` / `Enable HUD` / `Start HUD` / `HUD on` / `HUD mode` / `Toggle HUD` | Opens the real-time vision HUD window with YOLO overlays. |
| `BT, close HUD` / `Hide HUD` / `HUD off` / `Dismiss HUD` / `Turn off HUD` / `Disable HUD` / `Stop HUD` / `Exit HUD` / `Close the HUD` / `Close camera` / `Close window` | Closes the HUD window. |

> **HUD features:** Live camera feed with Titanfall-inspired corner brackets, YOLO object detection bounding boxes, and detection count status bar.

---

## VPN / Cloak Control

| Command | What It Does |
|---------|-------------|
| `BT, engage cloak` / `Turn on VPN` / `Enable VPN` / `Activate cloak` / `Put on cloak` / `Start VPN` / `Cloak on` / `VPN on` | Connects the VPN (ProtonVPN). Takes ~25-35s for WireGuard handshake. |
| `BT, disengage cloak` / `Turn off VPN` / `Disable VPN` / `Deactivate cloak` / `Take off cloak` / `Stop VPN` / `Cloak off` / `VPN off` | Disconnects the VPN. |
| `BT, cloak status` / `VPN status` / `Are you cloaked?` / `Is the VPN on?` / `Is VPN connected?` / `Are we protected?` / `Is my connection secure?` | Reports current VPN connection state with diagnostics. |
| `BT, cloak details` / `VPN details` | Detailed cloak diagnostics (server, network, auto-cloak). |
| `BT, enable auto-cloak` / `Turn on auto-cloak` / `Enable VPN auto-connect` | Auto-warns on public Wi-Fi without VPN. |
| `BT, disable auto-cloak` / `Turn off auto-cloak` / `Disable VPN auto-connect` | Turns off auto-cloak warnings. |
| `BT, enable cloak monitor` / `Turn on cloak monitor` / `Enable VPN monitor` | Starts the VPN monitoring service. |
| `BT, disable cloak monitor` / `Turn off cloak monitor` / `Disable VPN monitor` | Stops the VPN monitoring service. |

> **Note:** ProtonVPN uses WireGuard via Apple NetworkExtension. The app must stay frontmost during the 20-second cryptographic handshake. BT handles this automatically.

---

## Protocol Brief — Task & Note Management

| Command | What It Does |
|---------|-------------|
| `BT, protocol brief` | Summary of active tasks, completed tasks, and notes. |
| `BT, add task [description]` / `Add todo [description]` / `New task [description]` / `New todo [description]` | Adds a new to-do item. |
| `BT, add to my todo list [description]` / `Put on my todo list [description]` / `Add to the todo list [description]` | Adds a task (flexible phrasing). |
| `BT, list tasks` / `What are my tasks?` / `List todos` / `Show tasks` / `Show todos` | Shows all active to-do items. |
| `BT, clear completed tasks` / `Clear done tasks` | Removes finished items from the list. |
| `BT, add note [text]` / `Make note [text]` / `Write note [text]` / `Take note [text]` | Saves a personal note. |
| `BT, list notes` / `Show notes` / `Read notes` / `View notes` | Displays recent notes. |
| `BT, set mission [description]` / `New mission [description]` / `Update mission [description]` | Sets or updates your current mission briefing. |
| `BT, what is the mission?` / `Mission status` / `Current mission` / `Mission brief` | Reads back the current mission. |
| `BT, clear mission` / `End mission` / `Delete mission` | Deletes the active mission briefing. |

---

## Logging — Personal & System Logs

| Command | What It Does |
|---------|-------------|
| `BT, make log [text]` / `Create log [text]` / `Write log [text]` / `Log this [text]` | Creates a personal pilot log entry. |
| `BT, make a BT log [text]` / `Create system log [text]` | Creates a system log entry (BT's own logs). |
| `BT, read my logs` / `View logs` / `Show logs` / `Check logs` / `What are my logs?` | Reads recent personal log entries. |
| `BT, read BT logs` / `Read system logs` / `View BT logs` | Reads BT-7274's system logs. |
| `BT, delete my logs` / `Clear logs` / `Remove logs` / `Erase logs` | Clears personal log entries. |
| `BT, delete BT logs` / `Clear system logs` | Clears BT's system log entries. |

---

## Travel & Directions

| Command | What It Does |
|---------|-------------|
| `BT, how do I get to [destination]?` / `How to get to [destination]?` / `Travel to [destination]` / `Route to [destination]` / `Directions to [destination]` | Travel options from your current location. |
| `BT, how far is [destination]?` / `How long to get to [destination]?` | Distance and travel time estimates. |
| `BT, best way to get to [destination]` / `Fastest way to get to [destination]` / `Options to get to [destination]` | Personalized route recommendations. |
| `BT, drive to [destination]` / `Fly to [destination]` / `Commute to [destination]` | Mode-specific travel queries. |

> **Note:** BT automatically factors in your real-world current location for all travel queries.

---

## System Maintenance & Settings

| Command | What It Does |
|---------|-------------|
| `BT, clear TTS cache` / `Clear cache` | Clears cached text-to-speech audio files. |
| `BT, enable weather warnings` / `Turn on weather warnings` / `Enable environmental warnings` / `Turn on environmental warnings` | Turns on environmental warning alerts. |
| `BT, disable weather warnings` / `Turn off weather warnings` / `Disable environmental warnings` / `Turn off environmental warnings` | Turns off environmental warning alerts. |
| `BT, enable protocol mode` / `Turn on protocol mode` / `Activate protocol mode` | Activates protocol mode (structured responses). |
| `BT, disable protocol mode` / `Turn off protocol mode` / `Deactivate protocol mode` | Deactivates protocol mode. |

---

## Social & Conversation

| Command | What It Does |
|---------|-------------|
| `Thanks, BT` / `Thank you` / `Thx` / `Appreciate it` / `Much appreciated` / `Grateful` | BT responds with "You're welcome, Pilot." (uses original voice clip if available). |
| `No` / `Nope` / `Never mind` | Cancels follow-up listening during a conversation chain. |
| `That's all` / `Goodbye` / `Bye` / `Bye BT` | Ends the conversation session. |
| `Nothing` / `Forget it` | Cancels the current command. |

---

## Follow-Up Conversation

After BT responds, you can continue the conversation without saying the wake word again (up to 2 follow-up turns within 8 seconds).

---

## Action Commands (Executed via LLM)

These are handled automatically when the LLM recognizes the intent:

| Intent | Example Phrases |
|--------|-----------------|
| **Open App** | `Open Safari`, `Open Spotify` |
| **Set Volume** | `Set volume to 50%` |
| **Run Shortcut** | `Run shortcut [name]` |
| **Web Search** | `Search the web for [query]` |

---

## Translation Protocol

| Command | What It Does |
|---------|-------------|
| `BT, start translating` / `Start translating [language]` / `Begin translating` / `Activate translator` / `Enable translator` / `Turn on translator` / `Start translation` / `Translate mode` / `Translation mode` / `I need a translator` / `Translate for me` / `Be my translator` / `Translation protocol` | Activates translation mode. BT listens and translates foreign speech to English. |
| `BT, translate from [lang] to [lang]` | Sets specific source and target languages. |
| `BT, stop translating` / `End translation` / `Stop translator` / `End translating` / `Deactivate translator` / `Disable translator` / `Turn off translator` / `Translator off` / `Translation off` / `Exit translate mode` / `Quit translating` / `Disengage translator` | Disengages translation mode. |
| `BT, translation status` / `Translator status` / `What language?` / `Detected language` / `Are you translating?` / `Is translation active?` | Reports current translation session status. |

> **How it works:** Once active, everything BT hears is treated as speech to translate. BT tells you what it means in English. When you reply, BT translates your English back into the foreign language so you can speak it.

---

## Background Monitoring (Automatic)

BT runs these monitors in the background without needing a command:

| Monitor | What It Tracks |
|---------|---------------|
| **Battery** | Warns at 50%, 20%, 10%, 5% battery levels |
| **Weather** | Warns about rain, thunderstorms, hail, extreme heat/cold |
| **VPN / Cloak** | Detects VPN connect/disconnect; auto-warns on public Wi-Fi |
| **Calendar** | Warns about upcoming events within 15 minutes |
| **Hardware** | Logs CPU, RAM, disk, thermal state, uptime |
| **Network** | Logs Wi-Fi SSID, signal, VPN state, latency, public network detection |
| **Voice** | Logs STT confidence, TTS metrics, wake events, pipeline errors |

---

## Quick Reference: Command Categories

```
Information    → weather, time, date, location, status, search, news
Battery        → battery status, power level
Calendar       → schedule, events, appointments, agenda, upcoming
Vision         → what do you see, analyze that, scan that, identify that, read this
HUD            → open/close HUD, pilot HUD, activate/deactivate HUD
Cloak/VPN      → engage/disengage cloak, cloak status, auto-cloak, cloak monitor
Protocol Brief → tasks, notes, mission, protocol brief, protocol mode
Logging        → make log, read logs, delete logs (pilot & BT)
Travel         → how to get to, how far is, best way to, directions to
Maintenance    → clear cache, weather warnings, protocol mode
Translation    → start translating, stop translating, translation status
Social         → thanks, goodbye, never mind
```

---

*Protocol 3: Protect the Pilot.*
