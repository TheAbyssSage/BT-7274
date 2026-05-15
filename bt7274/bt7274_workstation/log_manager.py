"""
Centralized Log Manager for BT-7274.

Provides a unified, clean directory structure for all logging:

  logs/
    conversations/      — Pilot↔BT interactions (JSONL, daily)
    bt_memory/          — BT's internal memory logs (text + JSONL)
    pilot_memory/       — Pilot's personal logs, todos, notes
    telemetry/          — System, health, and voice telemetry
      system/           — Hardware, network, battery, VPN, weather (JSONL)
                           - hardware: CPU, RAM, thermal, disk usage snapshots
                           - network: Wi-Fi, VPN, latency, public-network events
      health/           — Environmental warnings, wellness alerts (JSONL)
      voice/            — Wake-word, STT confidence, command metadata (JSONL)
    vision/             — Visual observations + archived images (JSONL)
    archive/            — Session cache archives (dated JSONL file entries)

All paths are resolved relative to the project root (two levels above this file).
"""

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Any


# ─── Root resolution ──────────────────────────────────────────────

# Resolve to the project root (3 levels up from this file:
#   log_manager.py -> workstation -> bt7274 -> project root)
_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
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
    """Hardware telemetry now stored in system telemetry directory."""
    return _ensure(LOGS_ROOT / "telemetry" / "system")


def get_telemetry_network_dir() -> Path:
    """Network telemetry now stored in system telemetry directory."""
    return _ensure(LOGS_ROOT / "telemetry" / "system")


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


# ─── Encryption key management ────────────────────────────────────

def get_encryption_key_path() -> Path:
    """Path to the encryption key file."""
    return LOGS_ROOT / "bt7274.key"


def ensure_encryption_key() -> bool:
    """Generate an encryption key if one doesn't exist. Returns True if new key was created."""
    from bt7274.bt7274_workstation.log_encryption import generate_key
    key_path = get_encryption_key_path()
    if not key_path.exists():
        key = generate_key()
        with open(key_path, "wb") as f:
            f.write(key)
        # Restrict permissions on the key file
        os.chmod(key_path, 0o600)
        return True
    return False


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


# ─── Telemetry consolidation and archive migration ──────────────

def migrate_telemetry_and_archive():
    """
    Migrate existing telemetry structure:
    - Move hardware/ files to system/
    - Move network/ files to system/
    - Consolidate archive/ timestamped folders to sessions.jsonl
    
    Safe to run multiple times (skips already-migrated items).
    """
    import shutil
    import json
    
    system_dir = get_telemetry_system_dir()
    moved_files = 0
    
    # 1. Move hardware telemetry files to system
    old_hardware_dir = LOGS_ROOT / "telemetry" / "hardware"
    if old_hardware_dir.exists():
        for file in old_hardware_dir.iterdir():
            if file.is_file():
                dest = system_dir / file.name
                if not dest.exists():
                    try:
                        shutil.move(str(file), str(dest))
                        moved_files += 1
                    except Exception:
                        pass
        # Clean up empty directory
        try:
            if not any(old_hardware_dir.iterdir()):
                old_hardware_dir.rmdir()
        except Exception:
            pass
    
    # 2. Move network telemetry files to system
    old_network_dir = LOGS_ROOT / "telemetry" / "network"
    if old_network_dir.exists():
        for file in old_network_dir.iterdir():
            if file.is_file():
                dest = system_dir / file.name
                if not dest.exists():
                    try:
                        shutil.move(str(file), str(dest))
                        moved_files += 1
                    except Exception:
                        pass
        # Clean up empty directory
        try:
            if not any(old_network_dir.iterdir()):
                old_network_dir.rmdir()
        except Exception:
            pass
    
    # 3. Consolidate archive structure (timestamped folders → sessions.jsonl)
    archive_dir = get_archive_dir()
    sessions_file = archive_dir / "sessions.jsonl"
    consolidated_entries = 0
    
    if archive_dir.exists():
        for item in sorted(archive_dir.iterdir()):
            # Skip if it's already the consolidated file
            if item.name == "sessions.jsonl":
                continue
            
            # If it's a timestamped folder (old format)
            if item.is_dir() and len(item.name) == 15:  # YYYYMMDD_HHMMSS format
                try:
                    # Read session_summary.json if it exists
                    summary_file = item / "session_summary.json"
                    if summary_file.exists():
                        with open(summary_file, "r", encoding="utf-8") as f:
                            entry = json.load(f)
                        # Ensure it has a timestamp
                        if "timestamp" not in entry:
                            entry["timestamp"] = item.name
                        # Append to consolidated sessions file
                        with open(sessions_file, "a", encoding="utf-8") as f:
                            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                        consolidated_entries += 1
                    
                    # Remove old folder (optional - keep for safety)
                    # shutil.rmtree(item)
                except Exception:
                    pass
    
    return {
        "telemetry_files_moved": moved_files,
        "archive_entries_consolidated": consolidated_entries,
    }


# ─── Log retention / pruning ──────────────────────────────────────

# Retention limits: max number of daily files to keep per category
LOG_RETENTION = {
    "conversations": 90,    # ~3 months of daily interaction logs
    "bt_memory": 90,        # ~3 months of BT memory logs
    "pilot_memory": 90,     # ~3 months of pilot memory logs
    "telemetry/system": 30, # ~1 month of system telemetry
    "telemetry/health": 30, # ~1 month of health telemetry
    "telemetry/voice": 30,  # ~1 month of voice telemetry
    "vision": 30,           # ~1 month of vision logs
}


def prune_old_logs() -> dict:
    """Remove old log files exceeding retention limits. Returns counts of removed files."""
    removed = {}
    for subpath, max_files in LOG_RETENTION.items():
        directory = LOGS_ROOT / subpath
        if not directory.exists():
            continue
        # Get all files, sorted oldest first
        files = sorted(
            [f for f in directory.iterdir() if f.is_file()],
            key=lambda p: p.stat().st_mtime
        )
        if len(files) <= max_files:
            continue
        to_remove = files[:len(files) - max_files]
        count = 0
        for f in to_remove:
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
        if count > 0:
            removed[subpath] = count
    return removed
