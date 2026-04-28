# BT-7274 VPN Cloak Monitor

## Overview

The VPN Cloak Monitor is BT-7274's tactical network-security subsystem. It continuously monitors the state of your Proton VPN connection, announces connect/disconnect events with immersive voice lines, detects public Wi-Fi networks, and logs all state changes to `logs/system_logs`.

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  macOS Network  │────▶│  VPNMonitor     │────▶│  BT-7274 TTS    │
│  Layer          │     │  (10s interval) │     │  Voice Lines    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  Wi-Fi SSID     │     │  logs/system/   │
│  Detection      │     │  bt7274_system_ │
│                 │     │  YYYY-MM-DD.log │
└─────────────────┘     └─────────────────┘
```

---

## Voice Lines

| Event | Voice Line |
|-------|-----------|
| **VPN Connected** | "Cloak engaged. Network traffic obfuscated." |
| **VPN Disconnected** | "Cloak offline. We are exposed, Pilot." |
| **Public Wi-Fi + No VPN** (auto-cloak) | "Warning: Public network detected ({ssid}). Recommend engaging cloak, Pilot." |

---

## Configuration (`config.yaml`)

```yaml
vpn:
  enabled: true
  interval: 10              # seconds between checks
  provider: protonvpn       # VPN provider name for logs
  auto_cloak: false         # Auto-warn on public Wi-Fi without VPN
```

### Options

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Master switch for VPN monitoring |
| `interval` | int | `10` | Seconds between state checks |
| `provider` | string | `"protonvpn"` | Provider label used in log entries |
| `auto_cloak` | bool | `false` | Warn when joining public Wi-Fi without VPN |

---

## Voice Commands

| Command | Action |
|---------|--------|
| "Enable auto cloak" | Turns on public Wi-Fi warnings |
| "Disable auto cloak" | Turns off public Wi-Fi warnings |
| "Enable VPN monitor" | Starts the VPN monitor thread |
| "Disable VPN monitor" | Stops the VPN monitor thread |
| "VPN status" / "Are we cloaked?" | Reports current VPN + Wi-Fi state |

---

## Log Format

All VPN state changes are written to `logs/system_logs/bt7274_system_YYYY-MM-DD.log`:

```
2025-04-28T12:00Z [vpn] connected proton-be-01 wifi=Starbucks_Guest
2025-04-28T12:15Z [vpn] disconnected wifi=Starbucks_Guest
```

Fields:
- **Timestamp**: ISO-8601 (`YYYY-MM-DDTHH:MZ`)
- **Tag**: `[vpn]`
- **State**: `connected` or `disconnected`
- **Server**: VPN server name (connected only)
- **Wi-Fi**: Current SSID (if detectable)

---

## Public Wi-Fi Detection

The monitor uses a keyword-based heuristic to identify likely public networks:

**Detected patterns:** `guest`, `public`, `free`, `wifi`, `hotspot`, `starbucks`, `mcdonalds`, `costa`, `kfc`, `burgerking`, `airport`, `hotel`, `motel`, `hilton`, `marriott`, `train`, `station`, `bus`, `terminal`, `library`, `cafe`, `coffee`, `restaurant`, `shopping`, `mall`, `store`

When `auto_cloak: true` and a public SSID is detected while the VPN is disconnected, BT-7274 issues a verbal warning once per network session.

---

## Detection Methods

The monitor uses two complementary strategies to detect VPN state on macOS:

1. **`scutil --nc list`** — Checks macOS network configuration for active VPN services matching "proton" or "vpn"
2. **`ifconfig`** — Scans for `utun*` tunnel interfaces with non-local IP addresses

This dual approach ensures detection works regardless of whether Proton VPN is registered as a system VPN service or operates via a userspace tunnel.

---

## File Location

- **Source**: `bt7274_workstation/vpn_monitor.py`
- **Pipeline integration**: `bt7274_assistant/pipeline.py` (step 10.3)
