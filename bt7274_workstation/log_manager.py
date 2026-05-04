"""
Centralized Log Manager for BT-7274.

Provides a unified, clean directory structure for all logging:

  logs/
    conversations/      — Pilot↔BT interactions (JSONL, daily)
    bt_memory/          — BT's internal memory logs (text + JSONL)
    pilot_memory/       — Pilot's personal logs, todos, notes
    telemetry/          — System, health, voice-command, network, hardware telemetry
      system/           — Battery, VPN, weather state changes (text logs)
      health/           — Environmental warnings, wellness alerts (JSONL)
      voice/            — Wake-word, STT confidence, command metadata (JSONL)
      hardware/         — CPU, RAM, thermal, disk usage snapshots (JSONL)
      network/          — Wi-Fi, VPN, latency, public-network events (JSONL)
    vision/             — Visual observations + archived images (JSONL)
    archive/            — Session cache archives (timestamped folders)

All paths are resolved relative to the project root (two levels above this file).
"""

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Any


# ─── Root resolution ──────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
LOGS_ROOT = _PROJECT_ROOT / "logs"

# ─── Sub-directory helpers ────────────────────────────────────────

def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_logs_root() -> Path:
    return _ensure(LOGS_ROOT)


def get_conversations_dir() -> Path:
    return _ensure(LOGS_ROOT / "conversations")


def get_bt_memory_dir() -> Path:
    return _ensure(LOGS_ROOT / "bt_memory")


def get_pilot_memory_dir() -> Path:
    return _ensure(LOGS_ROOT / "pilot_memory")


def get_telemetry_dir() -> Path:
    return _ensure(LOGS_ROOT / "telemetry")


def get_telemetry_system_dir() -> Path:
    return _ensure(LOGS_ROOT / "telemetry" / "system")


def get_telemetry_health_dir() -> Path:
    return _ensure(LOGS_ROOT / "telemetry" / "health")


def get_telemetry_voice_dir() -> Path:
    return _ensure(LOGS_ROOT / "telemetry" / "voice")


def get_telemetry_hardware_dir() -> Path:
    return _ensure(LOGS_ROOT / "telemetry" / "hardware")


def get_telemetry_network_dir() -> Path:
    return _ensure(LOGS_ROOT / "telemetry" / "network")


def get_vision_dir() -> Path:
    return _ensure(LOGS_ROOT / "vision")


def get_archive_dir() -> Path:
    return _ensure(LOGS_ROOT / "archive")


# ─── Daily file helpers ───────────────────────────────────────────

def daily_jsonl_path(directory: Path, prefix: str) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    return directory / f"{prefix}_{today}.jsonl"


def daily_log_path(directory: Path, prefix: str) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    return directory / f"{prefix}_{today}.log"


# ─── Atomic JSONL append ──────────────────────────────────────────

def append_jsonl(path: Path, entry: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def append_log(path: Path, line: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} {line}\n")
        return True
    except Exception:
        return False


# ─── Deduplication helper ─────────────────────────────────────────

class RecentHashSet:
    """Keeps a rolling set of recent hashes to avoid duplicate writes."""

    def __init__(self, max_size: int = 50):
        self._hashes: set[str] = set()
        self._order: list[str] = []
        self._max = max_size

    def is_duplicate(self, key: str) -> bool:
        if key in self._hashes:
            return True
        self._hashes.add(key)
        self._order.append(key)
        if len(self._order) > self._max:
            oldest = self._order.pop(0)
            self._hashes.discard(oldest)
        return False

    def hash_content(self, *parts: str) -> str:
        content = "|".join(p.strip().lower() for p in parts)
        return hashlib.md5(content.encode("utf-8")).hexdigest()[:16]


# ─── Legacy migration helper ──────────────────────────────────────

def migrate_legacy_logs():
    """
    One-shot migration from old flat log layout to new hierarchy.
    Moves existing files into their new homes without overwriting.
    Safe to run multiple times (skips already-migrated files).
    """
    legacy_map = {
        LOGS_ROOT / "bt-pilot_interactions": get_conversations_dir(),
        LOGS_ROOT / "bt_logs": get_bt_memory_dir(),
        LOGS_ROOT / "pilot_logs": get_pilot_memory_dir(),
        LOGS_ROOT / "system_logs": get_telemetry_system_dir(),
        LOGS_ROOT / "pilot_health": get_telemetry_health_dir(),
        LOGS_ROOT / "pilot_voice_commands": get_telemetry_voice_dir(),
        LOGS_ROOT / "bt_vision": get_vision_dir(),
        LOGS_ROOT / "session_archive": get_archive_dir(),
    }

    moved = 0
    skipped = 0
    for old_dir, new_dir in legacy_map.items():
        if not old_dir.exists():
            continue
        for item in old_dir.iterdir():
            dest = new_dir / item.name
            if dest.exists():
                skipped += 1
                continue
            try:
                if item.is_dir():
                    import shutil
                    shutil.move(str(item), str(dest))
                else:
                    item.rename(dest)
                moved += 1
            except Exception:
                skipped += 1

    # Clean up empty legacy dirs (and other known obsolete dirs)
    obsolete_dirs = [
        *list(legacy_map.keys()),
        LOGS_ROOT / "bt_brief",
        LOGS_ROOT / "bt_workstation",
        LOGS_ROOT / "pilot_notes",
        LOGS_ROOT / "pilot_todo",
        LOGS_ROOT / "pilot_voice_commands",
    ]
    for old_dir in obsolete_dirs:
        if old_dir.exists() and not any(old_dir.iterdir()):
            try:
                old_dir.rmdir()
            except Exception:
                pass

    return {"moved": moved, "skipped": skipped}


# ─── Directory listing helper ─────────────────────────────────────

def list_log_structure() -> dict:
    """Return a human-readable summary of the current log tree."""
    root = get_logs_root()
    result: dict[str, Any] = {}
    for sub in sorted(root.iterdir()):
        if sub.is_dir():
            files = list(sub.rglob("*"))
            result[sub.name] = {
                "files": len([f for f in files if f.is_file()]),
                "size_kb": round(sum(f.stat().st_size for f in files if f.is_file()) / 1024, 1),
            }
            # Nested telemetry dirs
            if sub.name == "telemetry":
                for nested in sorted(sub.iterdir()):
                    if nested.is_dir():
                        nfiles = list(nested.rglob("*"))
                        result[sub.name][nested.name] = {
                            "files": len([f for f in nfiles if f.is_file()]),
                            "size_kb": round(sum(f.stat().st_size for f in nfiles if f.is_file()) / 1024, 1),
                        }
    return result


def get_log_tree() -> str:
    """Return a formatted ASCII tree of the log directory."""
    root = get_logs_root()
    lines = [f"{root.name}/"]
    for sub in sorted(root.iterdir()):
        if sub.is_dir():
            files = list(sub.rglob("*"))
            file_count = len([f for f in files if f.is_file()])
            size_kb = round(sum(f.stat().st_size for f in files if f.is_file()) / 1024, 1)
            lines.append(f"  ├── {sub.name}/  ({file_count} files, {size_kb} KB)")
            if sub.name == "telemetry":
                for nested in sorted(sub.iterdir()):
                    if nested.is_dir():
                        nfiles = list(nested.rglob("*"))
                        nf_count = len([f for f in nfiles if f.is_file()])
                        nsize_kb = round(sum(f.stat().st_size for f in nfiles if f.is_file()) / 1024, 1)
                        lines.append(f"  │   ├── {nested.name}/  ({nf_count} files, {nsize_kb} KB)")
    return "\n".join(lines)
