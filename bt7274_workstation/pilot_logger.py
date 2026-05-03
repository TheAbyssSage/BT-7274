"""
Pilot Logger for BT-7274 Voice Assistant.

Handles free-form pilot logs and BT internal logs.
- Pilot logs: logs/pilot_memory/<name>_<date>.log or logs/pilot_memory/pilot_logs.md
- BT logs: logs/bt_memory/<name>_<date>.log

Each entry includes a timestamp, raw text, and optional tags.
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from bt7274_workstation.log_manager import (
    get_pilot_memory_dir,
    get_bt_memory_dir,
)


class PilotLogger:
    """Logger for Pilot and BT free-form text logs."""

    def __init__(self, base_log_dir: Optional[str] = None):
        if base_log_dir is None:
            self.pilot_logs_dir = get_pilot_memory_dir()
            self.bt_logs_dir = get_bt_memory_dir()
        else:
            self.base_log_dir = Path(base_log_dir)
            self.pilot_logs_dir = self.base_log_dir / "pilot_memory"
            self.bt_logs_dir = self.base_log_dir / "bt_memory"
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure log directories exist."""
        self.pilot_logs_dir.mkdir(parents=True, exist_ok=True)
        self.bt_logs_dir.mkdir(parents=True, exist_ok=True)
        # Also ensure legacy dirs exist for backward-compat reads
        legacy_pilot = self.pilot_logs_dir.parent / "pilot_logs"
        legacy_bt = self.bt_logs_dir.parent / "bt_logs"
        legacy_pilot.mkdir(parents=True, exist_ok=True)
        legacy_bt.mkdir(parents=True, exist_ok=True)

    def _sanitize_name(self, name: str) -> str:
        """Sanitize a log name for use in filenames."""
        # Replace spaces with underscores, remove non-alphanumeric except dash/underscore
        sanitized = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_').lower()
        return sanitized or "untitled"

    def _format_entry(self, text: str, tags: Optional[list[str]] = None) -> str:
        """Format a log entry with timestamp and optional tags."""
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        tag_str = ""
        if tags:
            tag_str = " [" + ", ".join(tags) + "]"
        return f"[{timestamp}]{tag_str} {text}\n"

    def log_pilot(
        self,
        text: str,
        name: Optional[str] = None,
        tags: Optional[list[str]] = None,
        use_single_file: bool = False,
    ) -> str:
        """
        Append a free-form entry to the pilot's personal log.

        Args:
            text: The raw log text.
            name: Optional log name (used in filename). Defaults to "pilot".
            tags: Optional list of tags (e.g., ["mission", "personal"]).
            use_single_file: If True, writes to pilot_logs.md instead of daily files.

        Returns:
            Confirmation message.
        """
        name = name or "pilot"
        entry = self._format_entry(text, tags)

        if use_single_file:
            log_file = self.pilot_logs_dir / "pilot_logs.md"
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            safe_name = self._sanitize_name(name)
            log_file = self.pilot_logs_dir / f"{safe_name}_{today}.log"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry)

        return f"Log entry saved to {log_file.name}."

    def log_bt(
        self,
        text: str,
        name: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> str:
        """
        Append a free-form entry to BT's internal system log.

        Args:
            text: The raw log text.
            name: Optional log name (used in filename). Defaults to "bt".
            tags: Optional list of tags.

        Returns:
            Confirmation message.
        """
        name = name or "bt"
        today = datetime.now().strftime("%Y-%m-%d")
        safe_name = self._sanitize_name(name)
        log_file = self.bt_logs_dir / f"{safe_name}_{today}.log"
        entry = self._format_entry(text, tags)

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry)

        return f"BT log entry saved to {log_file.name}."

    def read_pilot_logs(
        self,
        name: Optional[str] = None,
        date: Optional[str] = None,
        lines: int = 20,
    ) -> str:
        """
        Read recent pilot log entries.

        Args:
            name: Log name to filter by.
            date: Specific date (YYYY-MM-DD) to read.
            lines: Number of recent lines to return.

        Returns:
            Formatted log entries or a message if none found.
        """
        if date:
            safe_name = self._sanitize_name(name or "pilot")
            log_file = self.pilot_logs_dir / f"{safe_name}_{date}.log"
            if not log_file.exists():
                return f"No pilot log found for {name or 'pilot'} on {date}."
            files = [log_file]
        else:
            # Gather all pilot log files, sorted newest first
            files = sorted(self.pilot_logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not files:
                # Check for single file
                single = self.pilot_logs_dir / "pilot_logs.md"
                if single.exists():
                    files = [single]
                else:
                    return "No pilot logs found."

        all_lines = []
        for log_file in files:
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    file_lines = f.readlines()
                all_lines.extend(reversed(file_lines))
                if len(all_lines) >= lines:
                    break
            except Exception:
                continue

        selected = all_lines[:lines]
        if not selected:
            return "No log entries found."

        return "".join(reversed(selected))

    def delete_pilot_logs(
        self,
        name: Optional[str] = None,
        date: Optional[str] = None,
    ) -> str:
        """
        Delete pilot log files.

        Args:
            name: Specific log name to delete. If None, deletes all pilot logs.
            date: Specific date (YYYY-MM-DD) to delete. If None, deletes all dates.

        Returns:
            Confirmation message.
        """
        deleted = []
        errors = []

        if date:
            safe_name = self._sanitize_name(name or "pilot")
            log_file = self.pilot_logs_dir / f"{safe_name}_{date}.log"
            if log_file.exists():
                try:
                    log_file.unlink()
                    deleted.append(log_file.name)
                except Exception as e:
                    errors.append(f"{log_file.name}: {e}")
            else:
                return f"No pilot log found for {name or 'pilot'} on {date}."
        elif name:
            safe_name = self._sanitize_name(name)
            for log_file in self.pilot_logs_dir.glob(f"{safe_name}_*.log"):
                try:
                    log_file.unlink()
                    deleted.append(log_file.name)
                except Exception as e:
                    errors.append(f"{log_file.name}: {e}")
        else:
            # Delete all pilot log files
            for log_file in self.pilot_logs_dir.glob("*.log"):
                try:
                    log_file.unlink()
                    deleted.append(log_file.name)
                except Exception as e:
                    errors.append(f"{log_file.name}: {e}")
            # Also delete the single file if it exists
            single_file = self.pilot_logs_dir / "pilot_logs.md"
            if single_file.exists():
                try:
                    single_file.unlink()
                    deleted.append(single_file.name)
                except Exception as e:
                    errors.append(f"{single_file.name}: {e}")

        if deleted:
            return f"Deleted {len(deleted)} pilot log file(s): {', '.join(deleted)}."
        elif errors:
            return f"Failed to delete logs: {', '.join(errors)}."
        else:
            return "No pilot logs found to delete."

    def delete_bt_logs(
        self,
        name: Optional[str] = None,
        date: Optional[str] = None,
    ) -> str:
        """
        Delete BT log files.

        Args:
            name: Specific log name to delete. If None, deletes all BT logs.
            date: Specific date (YYYY-MM-DD) to delete. If None, deletes all dates.

        Returns:
            Confirmation message.
        """
        deleted = []
        errors = []

        if date:
            safe_name = self._sanitize_name(name or "bt")
            log_file = self.bt_logs_dir / f"{safe_name}_{date}.log"
            if log_file.exists():
                try:
                    log_file.unlink()
                    deleted.append(log_file.name)
                except Exception as e:
                    errors.append(f"{log_file.name}: {e}")
            else:
                return f"No BT log found for {name or 'bt'} on {date}."
        elif name:
            safe_name = self._sanitize_name(name)
            for log_file in self.bt_logs_dir.glob(f"{safe_name}_*.log"):
                try:
                    log_file.unlink()
                    deleted.append(log_file.name)
                except Exception as e:
                    errors.append(f"{log_file.name}: {e}")
        else:
            # Delete all BT log files
            for log_file in self.bt_logs_dir.glob("*.log"):
                try:
                    log_file.unlink()
                    deleted.append(log_file.name)
                except Exception as e:
                    errors.append(f"{log_file.name}: {e}")

        if deleted:
            return f"Deleted {len(deleted)} BT log file(s): {', '.join(deleted)}."
        elif errors:
            return f"Failed to delete logs: {', '.join(errors)}."
        else:
            return "No BT logs found to delete."

    def read_bt_logs(
        self,
        name: Optional[str] = None,
        date: Optional[str] = None,
        lines: int = 20,
    ) -> str:
        """
        Read recent BT internal log entries.

        Args:
            name: Log name to filter by.
            date: Specific date (YYYY-MM-DD) to read.
            lines: Number of recent lines to return.

        Returns:
            Formatted log entries or a message if none found.
        """
        if date:
            safe_name = self._sanitize_name(name or "bt")
            log_file = self.bt_logs_dir / f"{safe_name}_{date}.log"
            if not log_file.exists():
                return f"No BT log found for {name or 'bt'} on {date}."
            files = [log_file]
        else:
            files = sorted(self.bt_logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not files:
                return "No BT logs found."

        all_lines = []
        for log_file in files:
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    file_lines = f.readlines()
                all_lines.extend(reversed(file_lines))
                if len(all_lines) >= lines:
                    break
            except Exception:
                continue

        selected = all_lines[:lines]
        if not selected:
            return "No log entries found."

        return "".join(reversed(selected))
