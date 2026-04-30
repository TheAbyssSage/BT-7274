# BT-7274 Pilot Command Reference

> **Wake Word:** Say any of the trigger phrases below to activate BT-7274 before giving a command.

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
| `BT, what's the forecast?` | Upcoming weather forecast (3 days). |
| `BT, forecast for [city]` | Forecast for a specific location. |
| `BT, what time is it?` | Current time. |
| `BT, what's the date?` / `What day is it?` | Current date and day. |
| `BT, where am I?` / `What's my location?` | Your current geographic location. |
| `BT, what's your status?` / `How are you doing?` | BT's systems status report (uses original voice clips). |
| `BT, search for [topic]` | Web search with BT summarizing results. |
| `BT, who won [event]?` | Real-time info lookup via web search. |
| `BT, tell me about [topic]` | General knowledge search. |
| `BT, what's the latest news?` | News summary from web search. |

---

## VPN / Cloak Control

| Command | What It Does |
|---------|-------------|
| `BT, engage cloak` / `Turn on VPN` | Connects the VPN (ProtonVPN). |
| `BT, disengage cloak` / `Turn off VPN` | Disconnects the VPN. |
| `BT, cloak status` / `VPN status` | Reports current VPN connection state. |
| `BT, enable auto-cloak` | Auto-warns on public Wi-Fi without VPN. |
| `BT, disable auto-cloak` | Turns off auto-cloak warnings. |
| `BT, enable cloak monitor` | Starts the VPN monitoring service. |
| `BT, disable cloak monitor` | Stops the VPN monitoring service. |

---

## Protocol Brief — Task & Note Management

| Command | What It Does |
|---------|-------------|
| `BT, protocol brief` | Summary of active tasks, completed tasks, and notes. |
| `BT, add task [description]` / `Add todo [description]` | Adds a new to-do item. |
| `BT, add to my todo list [description]` | Adds a task (flexible phrasing). |
| `BT, list tasks` / `What are my tasks?` | Shows all active to-do items. |
| `BT, clear completed tasks` | Removes finished items from the list. |
| `BT, add note [text]` / `Make note [text]` | Saves a personal note. |
| `BT, list notes` / `Show notes` | Displays recent notes. |
| `BT, set mission [description]` | Sets or updates your current mission briefing. |
| `BT, what is the mission?` / `Mission status` | Reads back the current mission. |
| `BT, clear mission` / `End mission` | Deletes the active mission briefing. |

---

## Logging — Personal & System Logs

| Command | What It Does |
|---------|-------------|
| `BT, make log [text]` | Creates a personal pilot log entry. |
| `BT, make a BT log [text]` | Creates a system log entry (BT's own logs). |
| `BT, read my logs` | Reads recent personal log entries. |
| `BT, read BT logs` | Reads BT-7274's system logs. |
| `BT, delete my logs` | Clears personal log entries. |
| `BT, delete BT logs` | Clears BT's system log entries. |

---

## Travel & Directions

| Command | What It Does |
|---------|-------------|
| `BT, how do I get to [destination]?` | Travel options from your current location. |
| `BT, how far is [destination]?` | Distance and travel time estimates. |
| `BT, best way to get to [destination]` | Personalized route recommendations. |

> **Note:** BT automatically factors in your real-world current location for all travel queries.

---

## System Maintenance & Settings

| Command | What It Does |
|---------|-------------|
| `BT, clear TTS cache` / `Clear cache` | Clears cached text-to-speech audio files. |
| `BT, enable weather warnings` | Turns on environmental warning alerts. |
| `BT, disable weather warnings` | Turns off environmental warning alerts. |
| `BT, enable protocol mode` | Activates protocol mode (structured responses). |
| `BT, disable protocol mode` | Deactivates protocol mode. |

---

## Social & Conversation

| Command | What It Does |
|---------|-------------|
| `Thanks, BT` / `Thank you` | BT responds with "You're welcome, Pilot." (uses original voice clip if available). |
| `No` / `Nope` / `Never mind` | Cancels follow-up listening during a conversation chain. |
| `That's all` / `Goodbye` / `Bye` | Ends the conversation session. |
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

## Quick Reference: Command Categories

```
Information    → weather, time, date, location, status, search
Cloak/VPN      → engage/disengage cloak, cloak status, auto-cloak
Protocol Brief → tasks, notes, mission, protocol brief
Logging        → make log, read logs, delete logs
Travel         → how to get to, how far is, best way to
Maintenance    → clear cache, weather warnings, protocol mode
Social         → thanks, goodbye, never mind
```

---

*Protocol 3: Protect the Pilot.*
